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
  - writes each mismatch of a compared name as a ledger record, which
    gap-ledger.py append accepts as it is; a mismatch for any other name is
    a warning, never a gap
  - grades each mismatch (#793, #816): Critical `signature-mismatch`, except
    a judge's `parameter-name` difference in a TS/JS, Vue, Go or Rust file
    (Low) and an `omitted-optional` difference on an inventory entry marked
    `signature_form: "partial"` (an Info `observation`); both still match.
    The script checks the extension and the inventory flag itself, so the
    tag alone never lowers a grade
  - reports a return annotation the body contradicts (#835 follow-up): an
    `annotation-contradicted` mismatch names its `evidence_line`, which the
    script checks comes after the declaration and, with --source-root,
    holds a `return` or an arrow function's expression body; then it is an
    Info `observation` titled `Annotation contradicted: {name}` that asks
    for no change to the skill, else a Critical one with a warning
  - plans each check at the declaration the skill cites (#781): for a name
    the surface records in several files, `plan --skill-dir` picks the one
    file the skill cites on a line naming it, and hands the judge every
    file as `candidates` when the citations do not settle it; a record with
    no file never wins, and a mismatch found at a candidate names its `file`;
    end to end (#830), the runner and the surface give a name two monorepo
    packages define one record per file, so the cited one is compared
  - compares a signature documented with no argument (#794): `params` of
    `""` or `[]` is a signature, and of a name listed twice the entry with
    non-empty `params` or a usage form (#826) is compared
  - offers a name's other documented forms that list members as its
    check's `alternatives` (#826), one form per meaning, grades each
    mismatch against the form its `form` names, by that form's own label,
    and keeps every form's mismatch; with --plan the forms are the plan's;
    and compares a component `constant` the inventory gives a usage form (#837)
The surface fixture is load-coverage-inputs.py surface output built from a
--mode full extraction, so a recipe's internal match is never compared.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "src" / "skf-test-skill" / "scripts"
SCRIPT = SCRIPTS / "score-signatures.py"
GAP_LEDGER = SCRIPTS / "gap-ledger.py"
HARD_GATE = SCRIPTS / "hard-gate.py"
LOADER = SCRIPTS / "load-coverage-inputs.py"
EXTRACTOR = REPO_ROOT / "src" / "shared" / "scripts" / "skf-extract-public-api.py"

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
    # #793: each mismatch carries the judge's difference (none here) and the severity the script graded
    assert out["mismatches"] == [{**MISMATCH, "file": "src/helper.ts", "difference": None, "severity": "Critical"}]
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


# --------------------------------------------------------------------------
# grading a mismatch (#793, #816)
# --------------------------------------------------------------------------

RENAME = {"name": "helper", "line": 1, "source_sig": "(value: number) => number",
          "documented_sig": "(x: number) => number", "issue": "the parameter is named 'value' in the source",
          "difference": "parameter-name"}
POSITIONAL = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".c", ".h", ".cc",
              ".cpp", ".cxx", ".hpp")


def _append_and_gate(tmp_path: Path, gaps: Path) -> dict:
    """Append the gap records to a ledger, as coverage-check §5b does, and run the hard gate on it."""
    ledger = tmp_path / "test-findings-20260101T000000Z-abcdef12.json"
    proc = subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage",
                           "coverage-check", "--input", str(gaps)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    proc = subprocess.run([sys.executable, str(HARD_GATE), "check", "--ledger", str(ledger), "--skill-name", "demo",
                           "--report-path", str(tmp_path / "report.md"), "--require-stage", "coverage-check"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    return json.loads(proc.stdout)


def test_a_ts_parameter_rename_is_a_low_gap_that_still_matches(tmp_path):
    """#793 (oms-uitripled GAP-001): a TS caller passes arguments by position, so a renamed parameter is a
    Low gap: the hard gate lets the run through, and Signature Accuracy counts the signature as matching."""
    inventory, surface = _files(tmp_path)
    results = _write(tmp_path / "s.txt", json.dumps({"file": "src/helper.ts", "signature_mismatches": [RENAME]}))
    gaps = tmp_path / "signature-gaps.json"
    proc = _run("score", "--inventory", inventory, "--surface", surface, "--results", results,
                "--gaps-output", str(gaps))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert (out["matchingSignatures"], out["totalDocumented"], out["signatureAccuracy"]) == (2, 2, 100.0)
    assert out["mismatches"] == [{**RENAME, "file": "src/helper.ts", "severity": "Low"}]
    [gap] = json.loads(gaps.read_text(encoding="utf-8"))
    assert (gap["severity"], gap["category"], gap["title"], gap["source"], gap["export"]) == (
        "Low", "signature-mismatch", "Signature mismatch: helper", "src/helper.ts:1", "helper")
    assert "(value: number) => number" in gap["remediation"]
    gate = _append_and_gate(tmp_path, gaps)
    assert (gate["gate"], gate["blocking_count"], gate["counts"]["Low"]) == ("passed", 0, 1)


@pytest.mark.parametrize("file, severity", [
    *[(f"src/helper{ext}", "Low") for ext in POSITIONAL],
    ("src\\Helper.TSX", "Low"),
    # Python has keyword arguments, and the script cannot see which parameters a caller must pass by position
    ("pkg/a.py", "Critical"),
    ("pkg/a.pyi", "Critical"),
    # a Vue component's documented parameters are props callers set by name
    ("src/Helper.vue", "Critical"),
    # these name arguments at the call
    ("src/Helper.kt", "Critical"),
    ("src/Helper.cs", "Critical"),
    ("src/Helper.swift", "Critical"),
    ("src/Helper.scala", "Critical"),
    ("src/helper.ts.bak", "Critical"),
], ids=lambda v: v if isinstance(v, str) and v not in ("Low", "Critical") else None)
def test_a_rename_is_low_only_in_a_language_without_keyword_arguments(file, severity):
    inventory = [{"name": "helper", "kind": "function", "params": "x: number", "return_type": "number"}]
    surface = [{"name": "helper", "kind": "function", "file": file, "line": 1}]
    out = mod.score(inventory, ["helper"], surface, [{"file": file, "signature_mismatches": [RENAME]}])
    assert [(m["difference"], m["severity"]) for m in out["mismatches"]] == [("parameter-name", severity)]
    assert [(g["severity"], g["category"]) for g in out["gapRecords"]] == [(severity, "signature-mismatch")]
    assert out["matchingSignatures"] == (1 if severity == "Low" else 0)


def test_a_rename_is_graded_at_the_file_the_surface_records():
    """The extension is the planned file's, the one the surface records for the export: a Python export the judge
    reports under a `.ts` path stays Critical, and so does a TS export reported at another file."""
    inventory = [{"name": "helper", "kind": "function", "params": "x", "return_type": "int"}]
    surface = [{"name": "helper", "kind": "function", "file": "pkg/helper.py", "line": 1}]
    out = mod.score(inventory, ["helper"], surface, [{"file": "pkg/helper.ts", "signature_mismatches": [RENAME]}])
    assert [(m["file"], m["severity"]) for m in out["mismatches"]] == [("pkg/helper.ts", "Critical")]
    assert out["matchingSignatures"] == 0
    surface = [{"name": "helper", "kind": "function", "file": "src/helper.ts", "line": 1}]
    out = mod.score(inventory, ["helper"], surface, [{"file": "src/other.ts", "signature_mismatches": [RENAME]}])
    assert [m["severity"] for m in out["mismatches"]] == ["Critical"]
    # the same path written with `\` is the planned file
    out = mod.score(inventory, ["helper"], surface, [{"file": "src\\helper.ts", "signature_mismatches": [RENAME]}])
    assert [m["severity"] for m in out["mismatches"]] == ["Low"]


RETURN_TYPE = {"name": "helper", "line": 1, "source_sig": "(value: number) => string",
               "documented_sig": "(x: number) => number", "issue": "the return type is string in the source"}


@pytest.mark.parametrize("entries", [[RENAME, RETURN_TYPE], [RETURN_TYPE, RENAME]],
                         ids=["tagged-first", "untagged-first"])
def test_one_declaration_reported_twice_keeps_its_most_severe_grade(tmp_path, entries):
    """A judge that reports a rename and a return-type difference of one declaration as two entries: every entry
    is graded and the Critical one wins, whichever comes first and whether one result file or two holds them."""
    inventory, surface = _files(tmp_path)
    one = _write(tmp_path / "one.txt", json.dumps({"file": "src/helper.ts", "signature_mismatches": entries}))
    first = _write(tmp_path / "first.txt", json.dumps({"file": "src/helper.ts", "signature_mismatches": entries[:1]}))
    second = _write(tmp_path / "second.txt", json.dumps({"file": "src/helper.ts",
                                                         "signature_mismatches": entries[1:]}))
    for results in ([one], [first, second]):
        args = [arg for path in results for arg in ("--results", path)]
        out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, *args).stdout)
        assert [(m["name"], m["severity"], m["difference"]) for m in out["mismatches"]] == [
            ("helper", "Critical", None)]
        assert (out["matchingSignatures"], out["signatureAccuracy"]) == (1, 50.0)
        assert [g["severity"] for g in out["gapRecords"]] == ["Critical"]
    # a Low and an Info entry of one declaration keep the Low one
    partial = [{**e, "signature_form": "partial"} if e["name"] == "helper" else e for e in INVENTORY["exports"]]
    omitted = {**RETURN_TYPE, "difference": "omitted-optional"}
    for pair in ([omitted, RENAME], [RENAME, omitted]):
        out = mod.score(partial, SURFACE["sets"]["all"], SURFACE["exports"],
                        [{"file": "src/helper.ts", "signature_mismatches": pair}])
        assert [m["severity"] for m in out["mismatches"]] == ["Low"]


@pytest.mark.parametrize("mismatch", [
    {k: v for k, v in RENAME.items() if k != "difference"},
    {**RENAME, "difference": None},
], ids=["absent", "null"])
def test_a_mismatch_with_no_difference_stays_critical(mismatch):
    """Without the judge's tag nothing is lowered: not in a TS file, not on a form the skill labels partial."""
    inventory = [{"name": "helper", "kind": "function", "params": "x: number", "return_type": "number",
                  "signature_form": "partial"}]
    surface = [{"name": "helper", "kind": "function", "file": "src/helper.ts", "line": 1}]
    out = mod.score(inventory, ["helper"], surface, [{"file": "src/helper.ts", "signature_mismatches": [mismatch]}])
    assert [(m["difference"], m["severity"]) for m in out["mismatches"]] == [(None, "Critical")]
    assert [g["severity"] for g in out["gapRecords"]] == ["Critical"]
    assert (out["matchingSignatures"], out["signatureAccuracy"]) == (0, 0.0)


CANVAS = {"name": "Canvas", "kind": "function", "params": "{ of, children }", "return_type": "JSX.Element",
          "description": "Props (simplified)."}
CANVAS_SURFACE = {"exports": [{"name": "Canvas", "kind": "function", "file": "code/blocks/Canvas.tsx", "line": 12,
                               "signatureLine": "export const Canvas: FC<CanvasProps> = (props) => {",
                               "origin": "extraction"}],
                  "sets": {"all": ["Canvas"]}}
OMITTED = {"name": "Canvas", "line": 12, "source_sig": "(props: { of?: Export; children?: ReactNode; layout?: Layout })"
           " => JSX.Element", "documented_sig": "({ of, children }) => JSX.Element",
           "issue": "the documented props leave out the optional 'layout'", "difference": "omitted-optional"}


def test_an_optional_member_a_partial_form_leaves_out_is_an_info_observation(tmp_path):
    """#816 (storybook GAP-002): the skill labels its form of Canvas's props partial, and the judge finds only
    an optional prop left out: an Info observation, no Critical gap, and Signature Accuracy 100."""
    inventory = _write(tmp_path / "inventory.json", {"exports": [{**CANVAS, "signature_form": "partial"}],
                                                     "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", CANVAS_SURFACE)
    plan = json.loads(_run("plan", "--inventory", inventory, "--surface", surface).stdout)
    assert plan["files"][0]["checks"][0]["documented"]["signature_form"] == "partial"
    results = _write(tmp_path / "s.txt", json.dumps({"file": "code/blocks/Canvas.tsx",
                                                     "signature_mismatches": [OMITTED]}))
    gaps = tmp_path / "signature-gaps.json"
    proc = _run("score", "--inventory", inventory, "--surface", surface, "--results", results,
                "--gaps-output", str(gaps))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert (out["matchingSignatures"], out["totalDocumented"], out["signatureAccuracy"]) == (1, 1, 100.0)
    assert [(m["difference"], m["severity"]) for m in out["mismatches"]] == [("omitted-optional", "Info")]
    [gap] = json.loads(gaps.read_text(encoding="utf-8"))
    assert (gap["severity"], gap["category"], gap["title"], gap["source"], gap["export"]) == (
        "Info", "observation", "Partial signature: Canvas", "code/blocks/Canvas.tsx:12", "Canvas")
    assert gap["remediation"].startswith("No change:")
    gate = _append_and_gate(tmp_path, gaps)
    assert (gate["gate"], gate["counts"]["Critical"], gate["counts"]["Info"]) == ("passed", 0, 1)


@pytest.mark.parametrize("form", [{}, {"signature_form": "full"}], ids=["no-form", "full"])
def test_an_optional_member_a_full_form_leaves_out_stays_critical(tmp_path, form):
    """A form the skill does not label partial is held to the source: the same omission stays Critical,
    whatever the judge tagged it."""
    inventory = _write(tmp_path / "inventory.json", {"exports": [{**CANVAS, **form}], "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", CANVAS_SURFACE)
    plan = json.loads(_run("plan", "--inventory", inventory, "--surface", surface).stdout)
    assert plan["files"][0]["checks"][0]["documented"] == {"params": "{ of, children }",
                                                           "return_type": "JSX.Element", **form}
    results = _write(tmp_path / "s.txt", json.dumps({"file": "code/blocks/Canvas.tsx",
                                                     "signature_mismatches": [OMITTED]}))
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--results", results).stdout)
    assert [(m["difference"], m["severity"]) for m in out["mismatches"]] == [("omitted-optional", "Critical")]
    assert [(g["severity"], g["category"]) for g in out["gapRecords"]] == [("Critical", "signature-mismatch")]
    assert (out["matchingSignatures"], out["signatureAccuracy"]) == (0, 0.0)


@pytest.mark.parametrize("entries, compared", [
    ([{**CANVAS, "signature_form": "partial", "params": "{ of }"}, CANVAS], CANVAS),
    ([CANVAS, {**CANVAS, "signature_form": "partial", "params": "{ of }"}], CANVAS),
    ([{**CANVAS, "signature_form": "partial", "params": "{ of }"}, {**CANVAS, "signature_form": "full"}],
     {**CANVAS, "signature_form": "full"}),
    ([{**CANVAS, "signature_form": "partial", "params": "{ of }"}, {**CANVAS, "signature_form": "partial"}],
     {**CANVAS, "signature_form": "partial", "params": "{ of }"}),
], ids=["partial-then-full", "full-then-partial", "partial-then-marked-full", "two-partial"])
def test_a_name_with_several_entries_is_compared_with_its_full_form(entries, compared):
    """The plan's `documented` prefers a full entry when a name has several, so a form the skill also gives
    in full is held to it, and a partial one only stands when no full form exists."""
    expected = {f: compared[f] for f in ("params", "return_type", "signature_form") if f in compared}
    assert mod.documented_signatures(entries) == {"Canvas": expected}
    out = mod.score(entries, ["Canvas"], CANVAS_SURFACE["exports"],
                    [{"file": "code/blocks/Canvas.tsx", "signature_mismatches": [OMITTED]}])
    assert [m["severity"] for m in out["mismatches"]] == ["Info" if expected.get("signature_form") == "partial"
                                                           else "Critical"]


# --------------------------------------------------------------------------
# a return annotation the body contradicts (#835 follow-up)
# --------------------------------------------------------------------------

VIZ_FILE = "cognee/api/v1/visualize/start_visualization_server.py"
VIZ_LINES = [f"# line {n}" for n in range(1, 25)]
VIZ_LINES[11] = "def visualization_server(port: int = 8001) -> Callable[[], Callable[[], None]]:"
VIZ_LINES[18] = "    return start_visualization_server(port)"
VIZ = {"name": "visualization_server", "kind": "function", "params": "port: int = 8001",
       "return_type": "Callable[[], None]"}
VIZ_SURFACE = {"exports": [{"name": "visualization_server", "kind": "function", "file": VIZ_FILE, "line": 12,
                            "signatureLine": VIZ_LINES[11], "origin": "extraction"}],
               "sets": {"all": ["visualization_server"]}}
CONTRADICTED = {"name": "visualization_server", "line": 12,
                "source_sig": "(port: int = 8001) -> Callable[[], Callable[[], None]]",
                "documented_sig": "(port: int = 8001) -> Callable[[], None]",
                "issue": "the declaration annotates a function that returns a function; the body returns the server's "
                         "stop function", "difference": "annotation-contradicted", "evidence_line": 19}


VIZ_TEXT = "\n".join(VIZ_LINES) + "\n"


def _contradiction_run(tmp_path: Path, mismatch: dict, text: str | None = VIZ_TEXT, source_root: bool = True,
                       entry: dict = VIZ, surface_records: list[dict] | None = None,
                       file: str = VIZ_FILE) -> tuple[subprocess.CompletedProcess, Path]:
    """score over one annotation-contradicted mismatch reported at `file`, whose source `text` sits there under the
    source tree, given as --source-root when asked."""
    root = tmp_path / "source"
    if text is not None:
        (root / file).parent.mkdir(parents=True, exist_ok=True)
        (root / file).write_bytes(text.encode("utf-8"))
    inventory = _write(tmp_path / "inventory.json", {"exports": [entry], "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", {**VIZ_SURFACE, **(
        {"exports": surface_records} if surface_records is not None else {})})
    results = _write(tmp_path / "s.txt", json.dumps({"file": file, "signature_mismatches": [mismatch]}))
    gaps = tmp_path / "signature-gaps.json"
    args = ["score", "--inventory", inventory, "--surface", surface, "--results", results, "--gaps-output", str(gaps)]
    if source_root:
        root.mkdir(parents=True, exist_ok=True)
        args += ["--source-root", str(root)]
    return _run(*args), gaps


@pytest.mark.parametrize("source_root", [True, False], ids=["checked-in-the-source", "no-source-root"])
def test_a_return_annotation_the_body_contradicts_is_an_info_observation(tmp_path, source_root):
    """#835 follow-up (cognee visualization_server): the skill documents what the body returns, and the source's
    annotation says otherwise. The judge reports it tagged with the body line; the script checks that line comes
    after the declaration and, with --source-root, holds the `return`, then grades an Info observation that asks
    for no change to the skill, so the source's contradiction is visible and the gate still passes."""
    proc, gaps = _contradiction_run(tmp_path, CONTRADICTED, source_root=source_root)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert (out["matchingSignatures"], out["totalDocumented"], out["signatureAccuracy"]) == (1, 1, 100.0)
    assert out["mismatches"] == [{**CONTRADICTED, "file": VIZ_FILE, "severity": "Info"}]
    assert not any("annotation-contradicted" in w for w in out["warnings"])
    [gap] = json.loads(gaps.read_text(encoding="utf-8"))
    assert (gap["severity"], gap["category"], gap["title"], gap["source"], gap["export"]) == (
        "Info", "observation", "Annotation contradicted: visualization_server", f"{VIZ_FILE}:12",
        "visualization_server")
    assert f"`{VIZ_FILE}:19`" in gap["issue"] and CONTRADICTED["source_sig"] in gap["issue"]
    assert gap["remediation"].startswith("No change to the skill:") and "upstream" in gap["remediation"]
    assert f"`{VIZ_FILE}:12`" in gap["remediation"]
    gate = _append_and_gate(tmp_path, gaps)
    assert (gate["gate"], gate["counts"]["Critical"], gate["counts"]["Info"]) == ("passed", 0, 1)


LATER_FUNCTION = {"name": "stop_server", "kind": "function", "file": VIZ_FILE, "line": 16,
                  "signatureLine": "def stop_server():", "origin": "extraction"}


@pytest.mark.parametrize("mismatch, text, kwargs, fact", [
    ({**CONTRADICTED, "evidence_line": 15}, VIZ_TEXT, {}, "evidence_line 15 does not start with `return`"),
    ({**CONTRADICTED, "evidence_line": 5}, VIZ_TEXT, {}, "evidence_line 5 is before the declaration"),
    ({**CONTRADICTED, "evidence_line": 12}, VIZ_TEXT, {},
     "evidence_line 12, the declaration line, has no expression body after its parameters"),
    ({**CONTRADICTED, "evidence_line": 90}, VIZ_TEXT, {}, "evidence_line 90 is past the end of the file (24 lines)"),
    (CONTRADICTED, None, {}, "evidence_line 19 is in no readable file under --source-root"),
    (CONTRADICTED, "\n".join([*VIZ_LINES[:18], "    # return start_visualization_server(port)"]), {},
     "evidence_line 19 does not start with `return`"),
    # the `return` belongs to a later function: the next surface record in the file bounds the evidence line
    (CONTRADICTED, VIZ_TEXT, {"surface_records": [*VIZ_SURFACE["exports"], LATER_FUNCTION]},
     "evidence_line 19 is not before the next declaration in the file, at line 16"),
    # a parameter difference is no annotation the body contradicts
    ({**CONTRADICTED, "documented_sig": "(port: str = 8001) -> Callable[[], None]"}, VIZ_TEXT, {},
     "its parameters differ: documented `(port: str = 8001)`, source `(port: int = 8001)`"),
    # a documented entry that states no return type claims none, so nothing contradicts it
    ({**CONTRADICTED, "documented_sig": "(port: int = 8001)"}, VIZ_TEXT,
     {"entry": {k: v for k, v in VIZ.items() if k != "return_type"}},
     "the documented signature states no return type"),
], ids=["line-not-a-return", "line-before-the-declaration", "the-declaration-line", "past-the-end", "no-such-file",
        "a-comment", "a-return-in-a-later-function", "a-parameter-difference", "no-documented-return-type"])
def test_a_contradiction_whose_facts_do_not_check_is_critical(tmp_path, mismatch, text, kwargs, fact):
    """The tag alone never lowers a grade: a documented entry with no return type, a parameter difference, an
    evidence line before the declaration or past the next one, or, with --source-root, one that does not start with
    `return` (a comment does not) or that the file lacks, is graded as an untagged mismatch, and a warning names
    the fact that failed at the declaration's line."""
    proc, gaps = _contradiction_run(tmp_path, mismatch, text, **kwargs)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert [(m["difference"], m["severity"]) for m in out["mismatches"]] == [("annotation-contradicted", "Critical")]
    assert (out["matchingSignatures"], out["signatureAccuracy"]) == (0, 0.0)
    [gap] = json.loads(gaps.read_text(encoding="utf-8"))
    assert (gap["severity"], gap["category"], gap["title"]) == (
        "Critical", "signature-mismatch", "Signature mismatch: visualization_server")
    [warning] = [w for w in out["warnings"] if "annotation-contradicted" in w]
    assert warning.startswith(f"{VIZ_FILE}:12: "), "the warning names the declaration's line, its fact no other"
    assert fact in warning and "tagged annotation-contradicted" in warning and "(Critical)" in warning, warning


def test_without_a_source_root_only_the_line_order_is_checked(tmp_path):
    """No --source-root: a line after the declaration and before the next one is the one line fact checked, so a
    line that holds no `return` still grades Info, while one before the declaration, or the declaration line
    itself (only the file can show its expression body), stays Critical."""
    proc, _ = _contradiction_run(tmp_path, {**CONTRADICTED, "evidence_line": 15}, source_root=False)
    assert [m["severity"] for m in json.loads(proc.stdout)["mismatches"]] == ["Info"]
    for line, fact in ((5, "evidence_line 5 is before the declaration"),
                       (12, "evidence_line 12 is the declaration line, which only --source-root can check")):
        proc, _ = _contradiction_run(tmp_path, {**CONTRADICTED, "evidence_line": line}, source_root=False)
        out = json.loads(proc.stdout)
        assert [m["severity"] for m in out["mismatches"]] == ["Critical"]
        assert any(fact in w for w in out["warnings"]), out["warnings"]


@pytest.mark.parametrize("line, returns", [
    ("  return x;", True),
    ("    return", True),
    ("return start(port)", True),
    ("  callback: () => void,", False),
    ("  type F = () => void;", False),
    ("    Some(x) => x,", False),
    ('  log("return value")', False),
    ("  x = 1  # return later", False),
    ("  if (ok) return x;", False),
    ("  // return x", False),
    ('  "return x"', False),
    ("  generator.return(x);", False),
    ("  returns = x", False),
    ("  return_value = x", False),
    ("  startServer(port);", False),
    ("", False),
], ids=["return", "a-bare-return", "unindented", "a-callback-parameter", "a-type-arrow", "a-match-arm", "a-string",
        "a-comment-after-code", "a-return-after-code", "a-line-comment", "a-string-line", "a-method-named-return",
        "a-longer-name", "a-name-starting-with-return", "an-arrow-body-on-a-later-line", "blank"])
def test_a_line_after_the_declaration_returns_only_when_it_starts_with_return(line, returns):
    """A body line returns only when its text starts with the `return` keyword: a type arrow, a callback parameter,
    a match arm, a string or a comment never does, nor does an arrow's expression body on a line of its own."""
    lines = ["export const make = (port: number) =>", line]
    assert mod._returns(lines, 2, 1) is returns


@pytest.mark.parametrize("line, returns", [
    ("export const make = (port: number) => startServer(port);", True),
    ("export const make = async (port: number): Promise<Stop> => startServer(port);", True),
    ("const make = <T,>(port: T): Stop => startServer(port)", True),
    ("export default (port) => startServer(port);", True),
    ("def make(port: int) -> Stop: return start(port)", True),
    ("async def make(port): return await start(port)", True),
    ("export const make = (port: number) => {", False),
    ("export const make = (port: number) =>", False),
    ("type F = () => void;", False),
    ("export type F = (port: number) => Stop;", False),
    ("  callback: () => void,", False),
    ("    Some(x) => x,", False),
    ("def make(port: int) -> Stop:", False),
    ("def make(port: int) -> Stop: pass  # return later", False),
    ("function make(port) {", False),
    ("fun make(port: Int) = start(port)", False),
], ids=["an-arrow", "an-async-arrow", "a-generic-arrow", "a-default-arrow", "a-one-line-def", "an-async-def",
        "an-arrow-block", "an-arrow-body-on-the-next-line", "a-type-arrow", "an-exported-type-arrow",
        "a-callback-parameter", "a-match-arm", "a-def", "a-def-with-another-body", "a-function-block",
        "a-kotlin-expression-body"])
def test_the_declaration_line_returns_only_with_its_own_expression_body(line, returns):
    """The declaration line itself returns when its expression body follows its parameters there: an arrow
    function's `=> expr` or a Python `def ...: return x`. A block body, a type arrow, a callback parameter, a match
    arm or another language's expression body does not."""
    assert mod._returns([line], 1, 1) is returns


ONE_LINERS = {
    "arrow": ("src/make.ts", "export const make = (port: number): Stop => startServer(port);",
              "(port: number) => Server", "(port: number) => Stop"),
    "def": ("pkg/make.py", "def make(port: int) -> Server: return start_server(port)",
            "(port: int) -> Server", "(port: int) -> Stop"),
}


@pytest.mark.parametrize("kind", list(ONE_LINERS))
def test_a_one_line_declaration_whose_body_returns_the_documented_type_is_info(tmp_path, kind):
    """A one-line arrow or `def` returns on its declaration line, so `evidence_line` may be that line, once
    --source-root shows the expression body after the parameters."""
    file, text, source_sig, documented_sig = ONE_LINERS[kind]
    entry = {"name": "make", "kind": "function", "params": "port", "return_type": "Stop"}
    record = {"name": "make", "kind": "function", "file": file, "line": 1, "signatureLine": text,
              "origin": "extraction"}
    mismatch = {"name": "make", "line": 1, "source_sig": source_sig, "documented_sig": documented_sig,
                "issue": "the annotation says Server; the body returns a Stop", "difference": "annotation-contradicted",
                "evidence_line": 1}
    proc, gaps = _contradiction_run(tmp_path, mismatch, text + "\n", entry=entry, surface_records=[record], file=file)
    out = json.loads(proc.stdout)
    assert [m["severity"] for m in out["mismatches"]] == ["Info"], out["warnings"]
    assert [g["title"] for g in json.loads(gaps.read_text(encoding="utf-8"))] == ["Annotation contradicted: make"]


@pytest.mark.parametrize("line, evidence, severity", [(30, 33, "Info"), (12, 33, "Critical")],
                         ids=["the-later-declaration", "the-earlier-declaration"])
def test_a_name_declared_twice_in_one_file_is_checked_at_the_declaration_the_mismatch_names(tmp_path, line, evidence,
                                                                                          severity):
    """Of two records of the name in the mismatch's file, the closest at or before its `line` is the declaration,
    and the other bounds it: a `return` after the second declaration belongs to it, not to the first."""
    lines = [f"# line {n}" for n in range(1, 40)]
    lines[11], lines[29], lines[32] = VIZ_LINES[11], VIZ_LINES[11], VIZ_LINES[18]
    records = [VIZ_SURFACE["exports"][0], {**VIZ_SURFACE["exports"][0], "line": 30}]
    proc, _ = _contradiction_run(tmp_path, {**CONTRADICTED, "line": line, "evidence_line": evidence},
                                 "\n".join(lines) + "\n", surface_records=records)
    out = json.loads(proc.stdout)
    assert [(m["line"], m["severity"]) for m in out["mismatches"]] == [(line, severity)]
    if severity == "Critical":
        assert any("evidence_line 33 is not before the next declaration in the file, at line 30" in w
                   for w in out["warnings"]), out["warnings"]


def test_a_name_declared_in_two_files_is_checked_at_the_mismatch_file(tmp_path):
    """A check with candidates: the mismatch found at the second file is checked at that file's declaration (line
    40), not at the first file's (line 50), and against that file's text."""
    other = "cognee/api/v2/visualize.py"
    lines = [f"# line {n}" for n in range(1, 50)]
    lines[39], lines[42] = VIZ_LINES[11], VIZ_LINES[18]
    records = [{**VIZ_SURFACE["exports"][0], "line": 50}, {**VIZ_SURFACE["exports"][0], "file": other, "line": 40}]
    proc, _ = _contradiction_run(tmp_path, {**CONTRADICTED, "line": 40, "evidence_line": 43},
                                 "\n".join(lines) + "\n", surface_records=records, file=other)
    out = json.loads(proc.stdout)
    assert [(m["file"], m["severity"]) for m in out["mismatches"]] == [(other, "Info")], out["warnings"]


def test_a_file_outside_the_source_root_is_never_read(tmp_path):
    """A mismatch whose file leaves --source-root (`../outside.py`) is not checked there, even when that file holds
    the `return`."""
    _write(tmp_path / "outside.py", VIZ_TEXT)
    proc, _ = _contradiction_run(tmp_path, CONTRADICTED, None, file="../outside.py",
                                 surface_records=[{**VIZ_SURFACE["exports"][0], "file": "../outside.py"}])
    out = json.loads(proc.stdout)
    assert [m["severity"] for m in out["mismatches"]] == ["Critical"]
    assert any("evidence_line 19 is in no readable file under --source-root" in w for w in out["warnings"])


@pytest.mark.parametrize("newline", ["\r\n", "\r"], ids=["crlf", "cr-only"])
def test_lines_are_counted_whatever_ends_them(tmp_path, newline):
    """A CRLF or a CR-only file has its `return` at the line an editor shows."""
    proc, _ = _contradiction_run(tmp_path, CONTRADICTED, newline.join(VIZ_LINES) + newline)
    out = json.loads(proc.stdout)
    assert [m["severity"] for m in out["mismatches"]] == ["Info"], out["warnings"]


def test_the_declaration_line_falls_back_to_the_mismatch_line():
    """With no surface record of the name at the mismatch's file (a fallback scan's name), the declaration line is
    the mismatch's own `line`; with records there but none at or before it, the first record's."""
    out = mod.score([VIZ], ["visualization_server"], VIZ_SURFACE["exports"],
                    [{"file": VIZ_FILE, "signature_mismatches": [{**CONTRADICTED, "line": 3, "evidence_line": 9}]}])
    assert [m["severity"] for m in out["mismatches"]] == ["Critical"], "line 9 is before the record's line 12"
    out = mod.score([VIZ], ["visualization_server"], [],
                    [{"file": VIZ_FILE, "exports_found": ["visualization_server"],
                      "signature_mismatches": [{**CONTRADICTED, "line": 3, "evidence_line": 9}]}])
    assert [m["severity"] for m in out["mismatches"]] == ["Info"]


def test_a_source_root_that_is_no_folder_exits_1_before_the_results_are_read(tmp_path):
    """A bad --source-root is refused (exit 1) before any result is read, so a result that breaks the schema does
    not turn it into exit 2."""
    inventory = _write(tmp_path / "inventory.json", {"exports": [VIZ], "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", VIZ_SURFACE)
    bad = _write(tmp_path / "bad.txt", "not json")
    for root in (str(tmp_path / "absent"), ""):
        proc = _run("score", "--inventory", inventory, "--surface", surface, "--source-root", root, "--results", bad)
        assert proc.returncode == 1 and "--source-root" in proc.stderr and proc.stdout == ""


# --------------------------------------------------------------------------
# the declaration a check reads (#781) and zero-argument entries (#794)
# --------------------------------------------------------------------------

DEFINE_MAIN = {"name": "defineMain", "kind": "function", "params": "config: StorybookConfig",
               "return_type": "StorybookConfig", "description": "Types the main config."}
ANGULAR = "code/frameworks/angular/src/node/index.ts"
REACT_VITE = "code/frameworks/react-vite/src/node/index.ts"
NAMESAKES = {"exports": [
    {"name": "defineMain", "kind": "function", "file": ANGULAR, "line": 3,
     "signatureLine": "export function defineMain(config: AngularConfig): AngularConfig {", "origin": "extraction"},
    {"name": "defineMain", "kind": "function", "file": REACT_VITE, "line": 3,
     "signatureLine": "export function defineMain(config: StorybookConfig): StorybookConfig {",
     "origin": "extraction"},
], "sets": {"all": ["defineMain"]}}


@pytest.mark.parametrize("tree", [
    {"SKILL.md": f"# Demo\n\n`defineMain(config)` types the main config [AST:{REACT_VITE}:L3].\n"},
    {"SKILL.md": "# Demo\n\nSee references.\n",
     "references/deep/frameworks.md": f"## defineMain\n\n[SRC:./{REACT_VITE}:L3-L9]\n\nTypes the config.\n"},
], ids=["skill-md", "a-heading-then-its-citation"])
def test_the_check_is_planned_at_the_declaration_the_skill_cites(tmp_path, tree):
    """#781 (storybook): the surface records `defineMain` in two framework packages, and angular's sorts first.
    The skill cites react-vite's, so the judge reads react-vite's declaration and no other."""
    for rel, text in tree.items():
        _write(tmp_path / "skill" / rel, text)
    inventory = _write(tmp_path / "inventory.json", {"exports": [DEFINE_MAIN], "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", NAMESAKES)
    proc = _run("plan", "--inventory", inventory, "--surface", surface, "--skill-dir", str(tmp_path / "skill"))
    assert proc.returncode == 0, proc.stderr
    plan = json.loads(proc.stdout)
    assert plan["compared"] == 1
    assert plan["files"] == [{"file": REACT_VITE, "checks": [{
        "name": "defineMain", "line": 3,
        "signatureLine": "export function defineMain(config: StorybookConfig): StorybookConfig {",
        "documented": {"params": "config: StorybookConfig", "return_type": "StorybookConfig"}}]}]


COMPOSE = {"name": "composeStories", "kind": "function", "params": "csfExports, projectAnnotations?",
           "return_type": "ComposedStories"}
REACT = "code/renderers/react/src/portable-stories.tsx"
VUE = "code/renderers/vue3/src/portable-stories.ts"
COMPOSE_RECORDS = [
    {"name": "composeStories", "kind": "function", "file": VUE, "line": 12,
     "signatureLine": "export function composeStories<T>(csfExports: T, projectAnnotations?: Annotations) {",
     "origin": "extraction"},
    {"name": "composeStories", "kind": "function", "file": REACT, "line": 40,
     "signatureLine": "export function composeStories<T>(csfExports: T, projectAnnotations?: Annotations) {",
     "origin": "extraction"},
]
CANDIDATES = [{"file": REACT, "line": 40, "signatureLine": COMPOSE_RECORDS[1]["signatureLine"]},
              {"file": VUE, "line": 12, "signatureLine": COMPOSE_RECORDS[0]["signatureLine"]}]


@pytest.mark.parametrize("skill_md", [
    f"# Demo\n\n`composeStories` for React [AST:{REACT}:L40] and for Vue [AST:{VUE}:L12].\n",
    f"# Demo\n\n`composeStories(csfExports)` composes.\n\nIt returns stories.\n\n`render` [AST:{REACT}:L40]\n",
    None,
], ids=["both-cited", "neither-cited", "no-skill-dir"])
def test_a_check_the_citations_do_not_settle_hands_the_judge_every_candidate(tmp_path, skill_md):
    """Two files cited, none, or no --skill-dir: the check stays at the first record and lists every record
    with a file, for the judge to read each."""
    args = []
    if skill_md is not None:
        _write(tmp_path / "skill" / "SKILL.md", skill_md)
        args = ["--skill-dir", str(tmp_path / "skill")]
    inventory = _write(tmp_path / "inventory.json", {"exports": [COMPOSE], "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", {"exports": COMPOSE_RECORDS, "sets": {"all": ["composeStories"]}})
    proc = _run("plan", "--inventory", inventory, "--surface", surface, *args)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["files"] == [{"file": REACT, "checks": [{
        "name": "composeStories", "line": 40, "signatureLine": COMPOSE_RECORDS[1]["signatureLine"],
        "documented": {"params": "csfExports, projectAnnotations?", "return_type": "ComposedStories"},
        "candidates": CANDIDATES}]}]


def test_a_record_with_no_file_never_wins_over_one_with_a_file():
    """A by-eye record with no file (or a blank one) sorted first and sent the check, and its grade, nowhere: the
    record with a file is the planned one, with no candidate, and a rename reported there is graded at it."""
    inventory = [{"name": "helper", "kind": "function", "params": "x: number", "return_type": "number"}]
    surface = [
        {"name": "helper", "kind": "function", "file": None, "line": None, "signatureLine": None, "origin": "metadata"},
        {"name": "helper", "kind": "function", "file": "  ", "line": None, "signatureLine": None, "origin": "per-file"},
        {"name": "helper", "kind": "function", "file": "src/helper.ts", "line": 1,
         "signatureLine": "export function helper(value: number): number {", "origin": "extraction"},
    ]
    assert mod.plan(inventory, ["helper"], surface)["files"] == [{"file": "src/helper.ts", "checks": [{
        "name": "helper", "line": 1, "signatureLine": "export function helper(value: number): number {",
        "documented": {"params": "x: number", "return_type": "number"}}]}]
    out = mod.score(inventory, ["helper"], surface, [{"file": "src/helper.ts", "signature_mismatches": [RENAME]}])
    assert [m["severity"] for m in out["mismatches"]] == ["Low"]


def test_a_mismatch_found_at_a_candidate_is_recorded_there(tmp_path):
    """The judge read both candidates of the check planned at React's file and matched neither: the mismatch it
    gives Vue's `file` is recorded at Vue's declaration, the same one Vue's own result reports, and a rename
    there is graded at Vue's file."""
    inventory = _write(tmp_path / "inventory.json", {"exports": [COMPOSE], "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", {"exports": COMPOSE_RECORDS, "sets": {"all": ["composeStories"]}})
    mismatch = {"name": "composeStories", "line": 12, "source_sig": "(csfExports: T, annotations?: Annotations)",
                "documented_sig": "(csfExports, projectAnnotations?)", "issue": "the second parameter is renamed"}
    at_react = _write(tmp_path / "s1.txt", json.dumps({"file": REACT, "signature_mismatches": [{**mismatch,
                                                                                               "file": VUE}]}))
    at_vue = _write(tmp_path / "s2.txt", json.dumps({"file": VUE, "signature_mismatches": [mismatch]}))
    gaps = tmp_path / "signature-gaps.json"
    proc = _run("score", "--inventory", inventory, "--surface", surface, "--results", at_react, "--results", at_vue,
                "--gaps-output", str(gaps))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert [(m["file"], m["line"], m["severity"]) for m in out["mismatches"]] == [(VUE, 12, "Critical")]
    [gap] = json.loads(gaps.read_text(encoding="utf-8"))
    assert (gap["source"], gap["export"]) == (f"{VUE}:12", "composeStories") and f"`{VUE}:12`" in gap["remediation"]
    renamed = {**mismatch, "file": VUE, "difference": "parameter-name"}
    out = mod.score([COMPOSE], ["composeStories"], COMPOSE_RECORDS,
                    [{"file": REACT, "signature_mismatches": [renamed]}])
    assert [(m["file"], m["severity"]) for m in out["mismatches"]] == [(VUE, "Low")]


def test_an_export_documented_with_no_argument_is_compared(tmp_path):
    """#794: `params` of `""` (the inventory contract's own form) or `[]` with no return type is a signature: both
    are planned, counted and compared, so a component documented as taking nothing is held to its source."""
    inventory = _write(tmp_path / "inventory.json", {"exports": [
        {"name": "noArgs", "kind": "function", "params": "", "description": "Takes none."},
        {"name": "noArgsList", "kind": "function", "params": [], "description": "Takes none."},
    ], "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", {"exports": [
        {"name": "noArgs", "kind": "function", "file": "src/a.tsx", "line": 1,
         "signatureLine": "export function noArgs(props: Props) {", "origin": "extraction"},
        {"name": "noArgsList", "kind": "function", "file": "src/a.tsx", "line": 5,
         "signatureLine": "export function noArgsList() {", "origin": "extraction"},
    ], "sets": {"all": ["noArgs", "noArgsList"]}})
    plan = json.loads(_run("plan", "--inventory", inventory, "--surface", surface).stdout)
    assert plan["compared"] == 2
    assert [(c["name"], c["documented"]) for c in plan["files"][0]["checks"]] == [
        ("noArgs", {"params": ""}), ("noArgsList", {"params": []})]
    results = _write(tmp_path / "s.txt", json.dumps({"file": "src/a.tsx", "signature_mismatches": [
        {"name": "noArgs", "line": 1, "source_sig": "(props: Props)", "documented_sig": "()",
         "issue": "the source takes props"}]}))
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--results", results).stdout)
    assert (out["matchingSignatures"], out["totalDocumented"], out["comparedNames"]) == (
        1, 2, ["noArgs", "noArgsList"])
    assert [(g["export"], g["severity"]) for g in out["gapRecords"]] == [("noArgs", "Critical")]


HELPER = {"name": "helper", "kind": "function", "params": "x: number", "return_type": "number"}


@pytest.mark.parametrize("entries, compared", [
    ([{"name": "helper", "kind": "function", "params": ""}, HELPER], HELPER),
    ([{"name": "helper", "kind": "function", "return_type": "number"}, HELPER], HELPER),
    ([{"name": "helper", "kind": "function", "params": "", "return_type": "number"}, HELPER], HELPER),
    ([HELPER, {"name": "helper", "kind": "function", "params": [], "return_type": "void"}], HELPER),
    ([{"name": "helper", "kind": "function", "params": "", "signature_form": "full"},
      {**HELPER, "signature_form": "partial"}], {**HELPER, "signature_form": "partial"}),
    ([{"name": "helper", "kind": "function", "params": ""},
      {"name": "helper", "kind": "function", "params": [], "return_type": "void"}], {"params": ""}),
], ids=["empty-then-full", "no-params-then-full", "empty-with-a-return-type-then-full", "full-then-empty-list", "empty-full-then-partial",
        "two-empty"])
def test_a_name_listed_twice_is_compared_with_the_entry_that_lists_its_parameters(entries, compared):
    """An entry with empty or no `params` and no usage form never hides one with parameters, whichever comes first
    and whatever its form; of two empty ones the first stands."""
    expected = {f: compared[f] for f in ("params", "return_type", "signature_form") if f in compared}
    assert mod.documented_signatures(entries) == {"helper": expected}


AVATAR_EMPTY = {"name": "Avatar", "kind": "function", "params": ""}
AVATAR_USAGE = {"name": "Avatar", "kind": "function",
                "usage_signature": "React.forwardRef<HTMLSpanElement, P>((props, ref) => ...)"}
X_PARTIAL = {"name": "X", "kind": "function", "params": "a", "signature_form": "partial"}
BLANK_USAGES = {"empty-list": {"name": "X", "kind": "hook", "usage_signature": []},
                "blank-in-a-list": {"name": "X", "kind": "hook", "usage_signature": [""]},
                "blank-string": {"name": "X", "kind": "function", "params": "", "usage_signature": "  "}}
BLANK_ROWS = [(pair, {"params": "a", "signature_form": "partial"})
              for blank in BLANK_USAGES.values() for pair in ([X_PARTIAL, blank], [blank, X_PARTIAL])]
BLANK_IDS = [f"partial-params-and-{key}-usage-{order}" for key in BLANK_USAGES for order in ("after", "before")]


@pytest.mark.parametrize("entries, compared", [
    ([AVATAR_EMPTY, AVATAR_USAGE], {"usage_signature": AVATAR_USAGE["usage_signature"]}),
    ([AVATAR_USAGE, AVATAR_EMPTY], {"usage_signature": AVATAR_USAGE["usage_signature"]}),
    ([{"name": "X", "kind": "function", "params": "a, b"},
      {"name": "X", "kind": "function", "usage_signature": "X(a)"}], {"params": "a, b"}),
    ([{"name": "X", "kind": "function", "usage_signature": "X(a)"},
      {"name": "X", "kind": "function", "params": "a, b"}], {"params": "a, b"}),
    ([{"name": "X", "kind": "function", "params": "a", "signature_form": "partial"},
      {"name": "X", "kind": "function", "usage_signature": "X(a, b)"}], {"usage_signature": "X(a, b)"}),
    ([{"name": "X", "kind": "function", "params": ""},
      {"name": "X", "kind": "function", "usage_signature": ["X(a)"]}], {"usage_signature": ["X(a)"]}),
    *BLANK_ROWS,
    ([{"name": "X", "kind": "function", "params": ""}], {"params": ""}),
], ids=["empty-then-usage", "usage-then-empty", "params-then-usage", "usage-then-params",
        "partial-params-then-full-usage", "empty-then-list-usage", *BLANK_IDS, "empty-alone"])
def test_a_usage_form_ranks_with_an_entry_that_lists_its_parameters(entries, compared):
    """#826: a forwardRef component the inventory records both with empty `params` and with its usage form is
    planned with the usage form in either order, so `Avatar()` is never compared with a forwardRef that takes
    props. Entries rank: one that lists parameters or gives a usage form (an empty or blank usage form gives none),
    then a full form before a partial one, then, of two full or two partial forms, one that lists parameters before
    one that gives only a usage form, then inventory order."""
    name = entries[0]["name"]
    assert mod.documented_signatures(entries) == {name: compared}
    plan = mod.plan(entries, [name], [{"name": name, "kind": "function", "file": "src/avatar.tsx", "line": 1}])
    assert [(c["name"], c["documented"]) for c in plan["files"][0]["checks"]] == [(name, compared)]


@pytest.mark.parametrize("line, planned", [
    # a citation of a file the surface does not record for the name settles nothing
    ("`defineMain(config)` [AST:code/frameworks/vue3-vite/src/node/index.ts:L3]", None),
    # a citation of the record file beside an unrelated one settles it
    (f"`defineMain(config)` [AST:{REACT_VITE}:L3] [SRC:code/core/src/types.ts:L40]", REACT_VITE),
], ids=["only-an-unrecorded-file", "the-record-file-and-an-unrelated-one"])
def test_only_a_cited_file_the_surface_records_settles_the_check(tmp_path, line, planned):
    _write(tmp_path / "skill" / "SKILL.md", f"# Demo\n\n{line}\n")
    inventory = _write(tmp_path / "inventory.json", {"exports": [DEFINE_MAIN], "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", NAMESAKES)
    proc = _run("plan", "--inventory", inventory, "--surface", surface, "--skill-dir", str(tmp_path / "skill"))
    assert proc.returncode == 0, proc.stderr
    [group] = json.loads(proc.stdout)["files"]
    [check] = group["checks"]
    if planned is None:
        assert group["file"] == ANGULAR and [c["file"] for c in check["candidates"]] == [ANGULAR, REACT_VITE]
    else:
        assert group["file"] == planned and "candidates" not in check


# #830: two monorepo packages that define composeStories, both in scope. Core's `./preview-api` subpath re-exports
# its own by name, so the runner's public row is core's; react's root entry point passes react's on through
# `export *`, an other definition.
CORE_PORTABLE = "code/core/src/preview-api/portable.ts"
REACT_PORTABLE = "code/renderers/react/src/portable.ts"
REACT_SIG = "export function composeStories(csfExports: ReactExports, projectAnnotations?: ReactAnnotations) {"
STORYBOOK_TREE = {
    "code/core/package.json": '{"name": "@sb/core", "exports": {"./preview-api": "./src/preview-api/index.ts"}}\n',
    "code/core/src/preview-api/index.ts": "export { composeStories } from './portable';\n",
    CORE_PORTABLE: ("export function composeStories(csfExports: CoreExports, projectAnnotations?: CoreAnnotations) {\n"
                    "  return csfExports;\n}\n"),
    "code/renderers/react/package.json": '{"name": "@sb/react", "exports": {".": "./src/index.ts"}}\n',
    "code/renderers/react/src/index.ts": "export * from './portable';\nexport type StoryObj = { args: object };\n",
    REACT_PORTABLE: REACT_SIG + "\n  return csfExports;\n}\n",
}


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
def test_a_name_two_monorepo_packages_define_is_compared_with_the_cited_declaration(tmp_path):
    """#830 (oms-storybook composeStories): the runner holds core's composeStories as the public row and react's
    as an other definition, the surface gives each a record, and the plan compares the skill's react form with
    the react declaration it cites, not with core's, which sorts first."""
    source = tmp_path / "src"
    for rel, text in STORYBOOK_TREE.items():
        _write(source / rel, text)
    extraction, surface = tmp_path / "extract-full.json", tmp_path / "surface.json"
    proc = subprocess.run([sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source),
                           "--include", "code/core/**", "--include", "code/renderers/react/**", "--tier", "Forge",
                           "--head-cap", "0", "--output", str(extraction)], capture_output=True, text=True,
                          timeout=600)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    proc = subprocess.run([sys.executable, str(LOADER), "surface", "--extraction", str(extraction), "--output",
                           str(surface)], capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr
    records = [r for r in json.loads(surface.read_text(encoding="utf-8"))["exports"] if r["name"] == "composeStories"]
    assert [r["file"] for r in records] == [CORE_PORTABLE, REACT_PORTABLE]
    _write(tmp_path / "skill" / "SKILL.md",
           f"# Demo\n\n`composeStories(csfExports, projectAnnotations?)` composes the stories "
           f"[AST:{REACT_PORTABLE}:L1].\n")
    inventory = _write(tmp_path / "inventory.json", {"exports": [COMPOSE], "cross_check_mismatches": []})
    proc = _run("plan", "--inventory", inventory, "--surface", str(surface), "--skill-dir", str(tmp_path / "skill"))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["files"] == [{"file": REACT_PORTABLE, "checks": [{
        "name": "composeStories", "line": 1, "signatureLine": REACT_SIG,
        "documented": {"params": "csfExports, projectAnnotations?", "return_type": "ComposedStories"}}]}]


@pytest.mark.parametrize("skill_dir", ["missing", "", "no-skill-md"])
def test_a_skill_dir_without_skill_md_exits_1(tmp_path, skill_dir):
    """A --skill-dir that is empty, absent or holds no SKILL.md is refused, as validate-inventory.py refuses its
    --skill-package: an empty one would read the working directory."""
    (tmp_path / "no-skill-md").mkdir()
    inventory = _write(tmp_path / "inventory.json", {"exports": [DEFINE_MAIN], "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", NAMESAKES)
    target = str(tmp_path / skill_dir) if skill_dir else ""
    proc = _run("plan", "--inventory", inventory, "--surface", surface, "--skill-dir", target)
    assert proc.returncode == 1 and "--skill-dir" in proc.stderr and proc.stdout == ""


def test_a_mismatch_file_the_plan_did_not_offer_is_not_taken(tmp_path):
    """The plan settled `defineMain` at react-vite's declaration, the one the skill cites. A mismatch the judge
    names angular's file for (or a file nowhere on the surface) is a warning and stays at the result's file,
    so no gap sits at a declaration the judge was never sent to, and a rename there is never Low at angular."""
    _write(tmp_path / "skill" / "SKILL.md", f"# Demo\n\n`defineMain(config)` [AST:{REACT_VITE}:L3]\n")
    inventory = _write(tmp_path / "inventory.json", {"exports": [DEFINE_MAIN], "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", NAMESAKES)
    plan = tmp_path / "signature-plan.json"
    assert _run("plan", "--inventory", inventory, "--surface", surface, "--skill-dir", str(tmp_path / "skill"),
                "--output", str(plan)).returncode == 0
    renamed = {"name": "defineMain", "line": 3, "source_sig": "(cfg: AngularConfig) => AngularConfig",
               "documented_sig": "(config: StorybookConfig) => StorybookConfig", "issue": "the parameter is renamed",
               "difference": "parameter-name"}
    for named in (ANGULAR, "nowhere/else.ts"):
        results = _write(tmp_path / "s.txt", json.dumps({"file": REACT_VITE, "signature_mismatches": [
            {**renamed, "file": named}]}))
        out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--plan", str(plan),
                              "--results", results).stdout)
        assert [(m["file"], m["line"]) for m in out["mismatches"]] == [(REACT_VITE, 3)]
        assert any(f"`{named}`, no file the plan offered its check at" in w for w in out["warnings"])
    # without the plan, the surface's records are the files offered: a file it lacks is still refused
    out = mod.score([DEFINE_MAIN], ["defineMain"], NAMESAKES["exports"],
                    [{"file": REACT_VITE, "signature_mismatches": [{**renamed, "file": "nowhere/else.ts"}]}])
    assert [m["file"] for m in out["mismatches"]] == [REACT_VITE]
    assert sum("no file the plan offered its check at" in w for w in out["warnings"]) == 1


def test_a_mismatch_file_is_compared_however_it_is_written():
    """`./code/...` and `code\\...` name the same candidate: one declaration, one gap, graded at that file."""
    renamed = {"name": "composeStories", "line": 12, "source_sig": "(csfExports: T, annotations?: Annotations)",
               "documented_sig": "(csfExports, projectAnnotations?)", "issue": "the second parameter is renamed",
               "difference": "parameter-name"}
    results = [{"file": REACT, "signature_mismatches": [{**renamed, "file": "./" + VUE}]},
               {"file": VUE.replace("/", "\\"), "signature_mismatches": [renamed]}]
    out = mod.score([COMPOSE], ["composeStories"], COMPOSE_RECORDS, results)
    assert [(m["file"], m["line"], m["severity"]) for m in out["mismatches"]] == [(VUE, 12, "Low")]
    assert [g["source"] for g in out["gapRecords"]] == [f"{VUE}:12"]
    assert not any("no file the plan offered" in w for w in out["warnings"])


def test_one_mismatch_per_candidate_keeps_the_closest():
    """A judge that reports the documented signature against each candidate gives one check one mismatch: the
    least severe, the candidate it is closest to."""
    far = {"name": "composeStories", "line": 40, "source_sig": "(csfExports: T, globalConfig: Config)",
           "documented_sig": "(csfExports, projectAnnotations?)", "issue": "a required second parameter",
           "file": REACT}
    near = {"name": "composeStories", "line": 12, "source_sig": "(csfExports: T, annotations?: Annotations)",
            "documented_sig": "(csfExports, projectAnnotations?)", "issue": "the second parameter is renamed",
            "difference": "parameter-name", "file": VUE}
    out = mod.score([COMPOSE], ["composeStories"], COMPOSE_RECORDS,
                    [{"file": REACT, "signature_mismatches": [far, near]}])
    assert [(m["file"], m["severity"]) for m in out["mismatches"]] == [(VUE, "Low")]
    assert (out["matchingSignatures"], out["totalDocumented"]) == (1, 1)
    out = mod.score([COMPOSE], ["composeStories"], COMPOSE_RECORDS,
                    [{"file": REACT, "signature_mismatches": [far, {**near, "difference": None}]}])
    assert [(m["file"], m["severity"]) for m in out["mismatches"]] == [(REACT, "Critical")], "first on a tie"


def test_empty_params_on_a_kind_that_takes_none_is_no_signature():
    """#794 is for a function documented as taking nothing: a `type` or `constant` entry with `params: ""` and no
    other field documents no signature, so it is not planned."""
    inventory = [{"name": "Mode", "kind": "type", "params": ""}, {"name": "VERSION", "kind": "constant", "params": ""}]
    surface = [{"name": "Mode", "kind": "type", "file": "src/a.ts", "line": 1},
               {"name": "VERSION", "kind": "constant", "file": "src/a.ts", "line": 2}]
    assert mod.documented_signatures(inventory) == {}
    assert mod.plan(inventory, ["Mode", "VERSION"], surface)["compared"] == 0


# --------------------------------------------------------------------------
# every documented form of a name (#826) and a component constant's form (#837)
# --------------------------------------------------------------------------

BRIEF = {"name": "Canvas", "kind": "function", "params": "{ of }", "description": "SKILL.md's quick form."}
# A typed props list claims it is complete: an optional prop it leaves out is an `omitted-optional` difference.
DETAILED = {"name": "Canvas", "kind": "function",
            "params": "{ of?: Export; meta?: Meta; sourceState?: SourceState; layout?: Layout }",
            "description": "The reference file's props."}
CANVAS_USAGE = {"name": "Canvas", "kind": "function", "usage_signature": "<Canvas of={Primary} />",
                "description": "SKILL.md's usage."}
# Storybook 7 renamed the prop `story` to `of`: a usage that still sets `story` really mismatches.
CANVAS_STORY = {"name": "Canvas", "kind": "function", "usage_signature": "<Canvas story={Primary} />",
                "description": "SKILL.md's usage, from Storybook 6."}
CANVAS_SOURCE_SIG = ("(props: { of?: Export; meta?: Meta; sourceState?: SourceState; layout?: Layout; "
                     "className?: string })")
# The detailed form, form 1, leaves out an optional prop of the source.
OMITS_CLASSNAME = {"name": "Canvas", "line": 12, "form": 1, "difference": "omitted-optional",
                   "source_sig": CANVAS_SOURCE_SIG, "documented_sig": f"({DETAILED['params']})",
                   "issue": "the typed props list leaves out the optional 'className'"}
# The usage, form 0, sets a prop the source does not declare.
SETS_STORY = {"name": "Canvas", "line": 12, "form": 0, "source_sig": CANVAS_SOURCE_SIG,
              "documented_sig": "<Canvas story={Primary} />", "issue": "the usage sets 'story', a prop Canvas lacks"}


@pytest.mark.parametrize("entries, alternatives", [
    ([BRIEF, DETAILED], [{"params": DETAILED["params"]}]),
    ([BRIEF, {**BRIEF, "description": "Repeated in a reference file."}], None),
    ([BRIEF], None),
], ids=["two-forms", "two-identical-forms", "one-form"])
def test_every_documented_form_of_a_name_is_offered_as_an_alternative(tmp_path, entries, alternatives):
    """#826 (storybook Canvas): SKILL.md writes `{ of }`, a reference file the full props list. Only the first was
    planned. The check keeps `{ of }` as `documented` and offers the other as `alternatives`, and the fallback scan
    gets it in `documentedAlternatives`; a name with one distinct form gets neither, and `documentedSignatures` is
    unchanged."""
    inventory = _write(tmp_path / "inventory.json", {"exports": entries, "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", CANVAS_SURFACE)
    plan = json.loads(_run("plan", "--inventory", inventory, "--surface", surface).stdout)
    [check] = plan["files"][0]["checks"]
    assert check["documented"] == {"params": "{ of }"}
    assert plan["documentedSignatures"] == {"Canvas": {"params": "{ of }"}}
    fallback = json.loads(_run("plan", "--inventory", inventory).stdout)
    assert fallback["documentedSignatures"] == plan["documentedSignatures"]
    if alternatives is None:
        assert "alternatives" not in check and fallback["documentedAlternatives"] == {}
    else:
        assert list(check) == ["name", "line", "signatureLine", "documented", "alternatives"]
        assert check["alternatives"] == alternatives
        assert fallback["documentedAlternatives"] == {"Canvas": alternatives}
    # a check that offers files and forms lists its alternatives before its candidates
    [check] = mod.plan([COMPOSE, {**COMPOSE, "params": "csfExports"}], ["composeStories"],
                       COMPOSE_RECORDS)["files"][0]["checks"]
    assert list(check) == ["name", "line", "signatureLine", "documented", "alternatives", "candidates"]
    assert check["alternatives"] == [{"params": "csfExports", "return_type": "ComposedStories"}]


@pytest.mark.parametrize("entries, forms", [
    ([BRIEF, {**BRIEF, "signature_form": "full"}], [{"params": "{ of }"}]),
    ([{**BRIEF, "signature_form": "full"}, BRIEF], [{"params": "{ of }", "signature_form": "full"}]),
    ([{**BRIEF, "params": ["a", "b"]}, {**BRIEF, "params": "a, b"}], [{"params": ["a", "b"]}]),
    ([{**BRIEF, "params": "{ of,\n  meta }"}, {**BRIEF, "params": "{ of, meta }"}], [{"params": "{ of,\n  meta }"}]),
    ([{**DETAILED, "signature_form": "partial"}, DETAILED], [{"params": DETAILED["params"]}]),
    ([DETAILED, {**DETAILED, "signature_form": "partial"}], [{"params": DETAILED["params"]}]),
    ([{**BRIEF, "signature_form": "partial"}, {**BRIEF, "params": "{ of, meta }"}, BRIEF],
     [{"params": "{ of, meta }"}, {"params": "{ of }"}]),
    ([{**BRIEF, "return_type": "JSX.Element"}, {**BRIEF, "return_type": "JSX.Element", "usage_signature": None}],
     [{"params": "{ of }", "return_type": "JSX.Element"}]),
    ([BRIEF, {**BRIEF, "usage_signature": [], "return_type": "  "}], [{"params": "{ of }"}]),
], ids=["full-label-and-none", "none-and-full-label", "list-and-joined-string", "whitespace", "partial-then-full",
        "full-then-partial", "partial-full-pair-around-another", "a-null-key", "an-empty-list-and-a-blank-key"])
def test_entries_that_say_the_same_thing_are_one_form(entries, forms):
    """Two entries that differ only by a `full` label, a list against its items joined, or spacing are one form, so
    no copy of a form is offered as its own alternative. Of two that differ only by the partial label, the full one
    stands, where the rank would have put it: a partial copy never lowers a full form's grade."""
    assert mod.documented_forms(entries) == {"Canvas": forms}
    assert mod.documented_signatures(entries) == {"Canvas": forms[0]}


@pytest.mark.parametrize("entries, documented", [
    ([{"name": "helper", "kind": "function", "params": ""}, HELPER], HELPER),
    ([{"name": "helper", "kind": "function", "return_type": "number"}, HELPER], HELPER),
    ([{"name": "helper", "kind": "function", "params": "", "return_type": "number"}, HELPER], HELPER),
    ([HELPER, {"name": "helper", "kind": "function", "params": [], "return_type": "void"}], HELPER),
    ([{"name": "helper", "kind": "function", "params": "", "signature_form": "full"},
      {**HELPER, "signature_form": "partial"}], {**HELPER, "signature_form": "partial"}),
    ([{"name": "helper", "kind": "function", "params": ""},
      {"name": "helper", "kind": "function", "params": [], "return_type": "void"}], {"params": ""}),
], ids=["empty-then-full", "no-params-then-full", "empty-with-a-return-type-then-full", "full-then-empty-list",
        "empty-full-then-partial", "two-empty"])
def test_a_form_that_lists_no_members_is_never_an_alternative(entries, documented):
    """A form with empty or no `params` and no usage form says nothing of what the name takes: a declaration that
    takes none would match it and hide a wrong parameter list. So it is never an alternative, and each row of the
    rank test above is planned with its `documented` form alone."""
    expected = {f: documented[f] for f in ("params", "return_type", "signature_form") if f in documented}
    assert mod.documented_forms(entries) == {"helper": [expected]}
    [check] = mod.plan(entries, ["helper"], [{"name": "helper", "kind": "function", "file": "src/helper.ts",
                                              "line": 1}])["files"][0]["checks"]
    assert check["documented"] == expected and "alternatives" not in check


@pytest.mark.parametrize("first, label, severity", [
    (CANVAS_USAGE, "partial", "Info"),
    (BRIEF, "partial", "Info"),
    (BRIEF, "full", "Critical"),
], ids=["usage-then-partial-props", "brief-then-partial-props", "brief-then-full-props"])
def test_a_mismatch_is_graded_against_the_form_it_names(tmp_path, first, label, severity):
    """#826 fixture (a): SKILL.md's form matches the declaration, which takes only optional props. The reference's
    typed props list, form 1, leaves out the optional `className`, so the judge reports it for form 1 and `score`
    grades it by that form's own label: partial, an Info observation (the gate passes, Signature Accuracy 100); full,
    Critical. With no `form`, or `form` 0, the same mismatch quotes form 1's text as its `documented_sig`, so it is
    graded against form 1 all the same, with a warning."""
    entries = [first, {**DETAILED, "signature_form": label}]
    inventory = _write(tmp_path / "inventory.json", {"exports": entries, "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", CANVAS_SURFACE)
    plan = json.loads(_run("plan", "--inventory", inventory, "--surface", surface).stdout)
    [check] = plan["files"][0]["checks"]
    assert check["documented"] == mod._form(first)
    assert check["alternatives"] == [{"params": DETAILED["params"], "signature_form": label}]
    results = _write(tmp_path / "s.txt", json.dumps({"file": "code/blocks/Canvas.tsx",
                                                     "signature_mismatches": [OMITS_CLASSNAME]}))
    gaps = tmp_path / "signature-gaps.json"
    proc = _run("score", "--inventory", inventory, "--surface", surface, "--results", results,
                "--gaps-output", str(gaps))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert [(m["difference"], m["severity"]) for m in out["mismatches"]] == [("omitted-optional", severity)]
    assert "form" not in out["mismatches"][0], "the mismatches[] keys the render reads are unchanged"
    category = "observation" if severity == "Info" else "signature-mismatch"
    [gap] = out["gapRecords"]
    assert (gap["severity"], gap["category"]) == (severity, category)
    assert gap["issue"].endswith(f"(documented form 2 of 2: `({DETAILED['params']})`)"), gap["issue"]
    assert gap["title"].endswith(" (form 2 of 2)"), gap["title"]
    assert out["signatureAccuracy"] == (100.0 if severity == "Info" else 0.0)
    assert not any("`form`" in w for w in out["warnings"]), out["warnings"]
    if severity == "Info":
        gate = _append_and_gate(tmp_path, gaps)
        assert (gate["gate"], gate["counts"]["Critical"], gate["counts"]["Info"]) == ("passed", 0, 1)
    unnamed = {k: v for k, v in OMITS_CLASSNAME.items() if k != "form"}
    for mismatch in (unnamed, {**unnamed, "form": None}, {**unnamed, "form": 0}):
        out = mod.score(entries, ["Canvas"], CANVAS_SURFACE["exports"],
                        [{"file": "code/blocks/Canvas.tsx", "signature_mismatches": [mismatch]}])
        assert [m["severity"] for m in out["mismatches"]] == [severity]
        assert "names `form` 0, whose text its `documented_sig` is not: graded against form 1, the one it quotes" in \
            "\n".join(out["warnings"])


@pytest.mark.parametrize("order", ["documented-first", "alternative-first"])
def test_each_form_that_does_not_match_is_reported(tmp_path, order):
    """A usage that sets a prop Canvas lacks (form 0) beside a typed list that leaves out an optional prop (form 1,
    labelled partial): each form is graded by its own label and each mismatch stands, two gaps whose title and Issue
    name the form, counted from 1, in one result file or two. The Info one never hides the Critical one, and two
    Critical ones at one declaration are two ledger records."""
    entries = [CANVAS_STORY, {**DETAILED, "signature_form": "partial"}]
    pair = [SETS_STORY, OMITS_CLASSNAME] if order == "documented-first" else [OMITS_CLASSNAME, SETS_STORY]
    for results in ([{"file": "code/blocks/Canvas.tsx", "signature_mismatches": pair}],
                    [{"file": "code/blocks/Canvas.tsx", "signature_mismatches": [m]} for m in pair]):
        out = mod.score(entries, ["Canvas"], CANVAS_SURFACE["exports"], results)
        assert [(m["documented_sig"], m["severity"]) for m in out["mismatches"]] == [
            ("<Canvas story={Primary} />", "Critical"), (f"({DETAILED['params']})", "Info")]
        assert (out["matchingSignatures"], out["totalDocumented"], out["signatureAccuracy"]) == (0, 1, 0.0)
        assert [(g["title"], g["issue"][g["issue"].rindex("(documented form"):]) for g in out["gapRecords"]] == [
            ("Signature mismatch: Canvas (form 1 of 2)", "(documented form 1 of 2: `<Canvas story={Primary} />`)"),
            ("Partial signature: Canvas (form 2 of 2)", f"(documented form 2 of 2: `({DETAILED['params']})`)")]
    gaps = _write(tmp_path / "signature-gaps.json", out["gapRecords"])
    ledger = tmp_path / "test-findings-20260101T000000Z-abcdef12.json"
    proc = subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage",
                           "coverage-check", "--input", gaps], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["appended"] == ["GAP-001", "GAP-002"]
    # one form reported twice keeps its most severe grade, and the other form's mismatch still stands
    out = mod.score(entries, ["Canvas"], CANVAS_SURFACE["exports"], [{"file": "code/blocks/Canvas.tsx",
                    "signature_mismatches": [OMITS_CLASSNAME, {**OMITS_CLASSNAME, "difference": None}, SETS_STORY]}])
    assert [m["severity"] for m in out["mismatches"]] == ["Critical", "Critical"]
    # two Critical gaps at one declaration: each form's title tells them apart, so the ledger keeps both
    assert [g["title"] for g in out["gapRecords"]] == ["Signature mismatch: Canvas (form 1 of 2)",
                                                       "Signature mismatch: Canvas (form 2 of 2)"]
    gaps = _write(tmp_path / "critical-gaps.json", out["gapRecords"])
    ledger = tmp_path / "test-findings-20260101T000000Z-bcdef123.json"
    proc = subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage",
                           "coverage-check", "--input", gaps], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    assert (json.loads(proc.stdout)["appended"], json.loads(proc.stdout)["duplicates"]) == (["GAP-001", "GAP-002"], [])


TYPED_FULL = {"name": "Canvas", "kind": "function", "params": "{ of?: Export; meta?: Meta }"}
TYPED_PARTIAL = {"name": "Canvas", "kind": "function", "params": "{ of?: Export }", "signature_form": "partial"}


@pytest.mark.parametrize("form, sig, severity", [
    (1, "({ of?: Export; meta?: Meta })", "Critical"),
    (1, "({  of?: Export  })", "Info"),
    (0, "{ of?: Export }", "Info"),
], ids=["index-of-the-partial-quoting-the-full-form", "honest-index", "index-of-the-full-quoting-the-partial-form"])
def test_a_form_label_lowers_a_grade_only_for_the_form_the_mismatch_quotes(form, sig, severity):
    """A judge that compared the full typed list but names `form` 1, the partial one (counting from 1, say), would
    turn a Critical into an Info by the index alone. The partial label lowers the grade only when the mismatch's
    `documented_sig` is that form's text (whitespace runs as one, outer parentheses off); otherwise a warning, and
    the mismatch is graded against the form it quotes."""
    mismatch = {"name": "Canvas", "line": 12, "form": form, "difference": "omitted-optional",
                "source_sig": "(props: { of?: Export; meta?: Meta; className?: string })", "documented_sig": sig,
                "issue": "the typed list leaves out the optional 'className'"}
    out = mod.score([TYPED_FULL, TYPED_PARTIAL], ["Canvas"], CANVAS_SURFACE["exports"],
                    [{"file": "code/blocks/Canvas.tsx", "signature_mismatches": [mismatch]}])
    assert [m["severity"] for m in out["mismatches"]] == [severity]
    honest = (form == 1) == (severity == "Info")
    assert any("whose text its `documented_sig` is not" in w for w in out["warnings"]) is not honest


def test_each_usage_of_a_list_is_a_form_of_its_own():
    """Two usages of one `usage_signature` list that both fail at one declaration are two mismatches: the
    `documented_sig` each quotes is part of the declaration's key."""
    entries = [{"name": "Canvas", "kind": "function", "usage_signature": ["<Canvas story={A} />",
                                                                           "<Canvas source={B} />"]}, TYPED_FULL]
    [usages] = [i for i, f in enumerate(mod.documented_forms(entries)["Canvas"]) if "usage_signature" in f]
    results = [{"file": "code/blocks/Canvas.tsx", "signature_mismatches": [
        {"name": "Canvas", "line": 12, "form": usages, "source_sig": "(props: { of?: Export })",
         "documented_sig": usage, "issue": f"sets a prop Canvas lacks: {usage}"}
        for usage in ("<Canvas story={A} />", "<Canvas source={B} />")]}]
    out = mod.score(entries, ["Canvas"], CANVAS_SURFACE["exports"], results)
    assert sorted(m["documented_sig"] for m in out["mismatches"]) == ["<Canvas source={B} />", "<Canvas story={A} />"]
    assert not any("whose text its `documented_sig` is not" in w for w in out["warnings"])


def test_naming_a_partial_alternative_never_lowers_a_critical():
    """A partial copy of the full form is the full form (the stricter label stands), so it offers no alternative a
    judge could name to turn the full form's Critical into an Info: the `form` is one the check never offered, a
    warning, and the mismatch is graded against the full form."""
    entries = [DETAILED, {**DETAILED, "signature_form": "partial", "description": "Props (simplified)."}]
    assert mod.documented_forms(entries) == {"Canvas": [{"params": DETAILED["params"]}]}
    out = mod.score(entries, ["Canvas"], CANVAS_SURFACE["exports"],
                    [{"file": "code/blocks/Canvas.tsx", "signature_mismatches": [OMITS_CLASSNAME]}])
    assert [m["severity"] for m in out["mismatches"]] == ["Critical"]
    assert (out["matchingSignatures"], out["signatureAccuracy"]) == (0, 0.0)
    assert any("names `form` 1, no form its check offered (0 to 0)" in w for w in out["warnings"])


@pytest.mark.parametrize("form", [2, 5])
def test_a_form_the_check_did_not_offer_is_a_warning(form):
    """A `form` past the forms the check offered names nothing the script can grade by: `warnings` names it, and
    the mismatch is graded against `documented` (full here, so Critical, where the partial alternative would have
    made it Info)."""
    entries = [BRIEF, {**DETAILED, "signature_form": "partial"}]
    mismatch = {**OMITS_CLASSNAME, "form": form, "documented_sig": "({ of, meta })"}  # the text of no form
    out = mod.score(entries, ["Canvas"], CANVAS_SURFACE["exports"],
                    [{"file": "code/blocks/Canvas.tsx", "signature_mismatches": [mismatch]}])
    assert [m["severity"] for m in out["mismatches"]] == ["Critical"]
    assert [w for w in out["warnings"] if "`form`" in w] == [
        f"code/blocks/Canvas.tsx:12: a signature mismatch for `Canvas` names `form` {form}, no form its check offered "
        "(0 to 1): graded against `documented`"]


def test_two_declarations_in_one_file_each_keep_their_mismatch():
    """A name with several forms declared twice in one file (a check with no candidates): a mismatch at each
    declaration stands, whatever form each names; nothing collapses across declarations."""
    entries = [CANVAS_USAGE, {**DETAILED, "signature_form": "partial"}]
    records = [*CANVAS_SURFACE["exports"], {**CANVAS_SURFACE["exports"][0], "line": 30}]
    second = {**OMITS_CLASSNAME, "line": 30, "difference": None, "issue": "the second declaration takes no `of`"}
    for later in (second, {**second, "form": 0}):
        out = mod.score(entries, ["Canvas"], records,
                        [{"file": "code/blocks/Canvas.tsx", "signature_mismatches": [OMITS_CLASSNAME, later]}])
        assert [(m["line"], m["severity"]) for m in out["mismatches"]] == [(12, "Info"), (30, "Critical")]
        assert [g["source"] for g in out["gapRecords"]] == ["code/blocks/Canvas.tsx:12", "code/blocks/Canvas.tsx:30"]


def test_a_check_with_candidates_and_alternatives_keeps_the_closest_candidate_of_each_form():
    """A name the citations do not settle (candidates) and documented in two forms: of each form's mismatches at the
    candidates, the least severe stands (a form matches when it matches any candidate), and each form keeps its
    own."""
    entries = [COMPOSE, {**COMPOSE, "params": "csfExports"}]
    far = {"name": "composeStories", "line": 40, "source_sig": "(csfExports: T, globalConfig: Config)",
           "documented_sig": "(csfExports, projectAnnotations?)", "issue": "a required second parameter",
           "file": REACT}
    near = {**far, "line": 12, "file": VUE, "source_sig": "(csfExports: T, annotations?: Annotations)",
            "issue": "the second parameter is renamed", "difference": "parameter-name"}
    brief = [{**m, "form": 1, "documented_sig": "(csfExports)", "difference": None,
              "issue": "leaves out a required parameter"} for m in (far, near)]
    out = mod.score(entries, ["composeStories"], COMPOSE_RECORDS,
                    [{"file": REACT, "signature_mismatches": [far, near, *brief]}])
    assert [(m["file"], m["documented_sig"], m["severity"]) for m in out["mismatches"]] == [
        (REACT, "(csfExports)", "Critical"), (VUE, "(csfExports, projectAnnotations?)", "Low")]
    assert (out["matchingSignatures"], out["totalDocumented"]) == (0, 1)


def test_an_annotation_contradicted_mismatch_is_checked_against_its_form(tmp_path):
    """The facts of an `annotation-contradicted` mismatch are the named form's: form 0 states a return type, so the
    tag checks and the mismatch is an Info observation; form 1 states none, so the same mismatch reported for it
    is Critical, with the warning that names the fact that failed."""
    (tmp_path / VIZ_FILE).parent.mkdir(parents=True)
    (tmp_path / VIZ_FILE).write_bytes(VIZ_TEXT.encode("utf-8"))
    entries = [VIZ, {"name": "visualization_server", "kind": "function", "params": "port"}]
    for form, sig, severity in ((0, "(port: int = 8001)", "Info"), (1, "(port)", "Critical")):
        out = mod.score(entries, ["visualization_server"], VIZ_SURFACE["exports"],
                        [{"file": VIZ_FILE, "signature_mismatches": [{**CONTRADICTED, "form": form,
                                                                      "documented_sig": sig}]}],
                        source_root=str(tmp_path))
        assert [m["severity"] for m in out["mismatches"]] == [severity]
        failed = [w for w in out["warnings"] if "the documented signature states no return type" in w]
        assert len(failed) == (1 if form == 1 else 0), out["warnings"]


def test_score_grades_by_the_forms_the_plan_offered(tmp_path):
    """With --plan, `score` grades by the forms the plan offered the judge, and warns when the inventory it is given
    holds others: here the plan offered the partial typed list as form 1, the inventory no longer does."""
    planned = _write(tmp_path / "planned.json", {"exports": [BRIEF, {**DETAILED, "signature_form": "partial"}],
                                                  "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", CANVAS_SURFACE)
    plan = tmp_path / "signature-plan.json"
    assert _run("plan", "--inventory", planned, "--surface", surface, "--output", str(plan)).returncode == 0
    inventory = _write(tmp_path / "inventory.json", {"exports": [BRIEF], "cross_check_mismatches": []})
    results = _write(tmp_path / "s.txt", json.dumps({"file": "code/blocks/Canvas.tsx",
                                                     "signature_mismatches": [OMITS_CLASSNAME]}))
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--plan", str(plan),
                          "--results", results).stdout)
    assert [m["severity"] for m in out["mismatches"]] == ["Info"]
    assert "`Canvas`: the plan offered 2 documented form(s), not the 1 the inventory gives: graded against the " \
           "plan's" in out["warnings"]
    assert mod.load_plan_forms(str(plan)) == {"Canvas": [{"params": "{ of }"},
                                                         {"params": DETAILED["params"], "signature_form": "partial"}]}
    # the plan of the inventory it is given: no warning
    assert _run("plan", "--inventory", inventory, "--surface", surface, "--output", str(plan)).returncode == 0
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--plan", str(plan),
                          "--results", results).stdout)
    assert not any("the plan offered" in w for w in out["warnings"]), out["warnings"]


AVATAR_CONSTANT = {"name": "Avatar", "kind": "constant", "description": "A forwardRef component.",
                   "usage_signature": "React.forwardRef<HTMLSpanElement, AvatarProps>((props, ref) => ...)"}
TABS_ALIAS = {"name": "Tabs", "kind": "constant", "usage_signature": '<Tabs defaultValue="account" />',
              "description": "const Tabs = TabsPrimitive.Root"}
BADGE_VARIANTS = {"name": "badgeVariants", "kind": "constant", "description": "The badge's cva classes."}


def test_a_component_constant_with_a_usage_signature_is_compared(tmp_path):
    """#837 (uitripled): the inventory contract records a `const` holding a component (a `forwardRef` call, an alias
    of another component) as a `constant` with the form the skill writes as `usage_signature`, and a data constant
    with none: the components are planned and scored, the data constant is not, so a mismatch reported for it is a
    warning and no gap."""
    inventory = _write(tmp_path / "inventory.json", {"exports": [AVATAR_CONSTANT, TABS_ALIAS, BADGE_VARIANTS],
                                                     "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", {"exports": [
        {"name": "Avatar", "kind": "constant", "file": "src/avatar.tsx", "line": 8,
         "signatureLine": "const Avatar = React.forwardRef<HTMLSpanElement, AvatarProps>(", "origin": "extraction"},
        {"name": "badgeVariants", "kind": "constant", "file": "src/badge.tsx", "line": 3,
         "signatureLine": "const badgeVariants = cva(", "origin": "extraction"},
        {"name": "Tabs", "kind": "constant", "file": "src/tabs.tsx", "line": 5,
         "signatureLine": "const Tabs = TabsPrimitive.Root", "origin": "extraction"},
    ], "sets": {"all": ["Avatar", "Tabs", "badgeVariants"]}})
    plan = json.loads(_run("plan", "--inventory", inventory, "--surface", surface).stdout)
    assert plan["compared"] == 2
    assert [(c["name"], c["documented"]) for g in plan["files"] for c in g["checks"]] == [
        ("Avatar", {"usage_signature": AVATAR_CONSTANT["usage_signature"]}),
        ("Tabs", {"usage_signature": TABS_ALIAS["usage_signature"]})]
    results = _write(tmp_path / "s.txt", json.dumps([
        {"file": "src/avatar.tsx", "signature_mismatches": [
            {"name": "Avatar", "line": 8, "source_sig": "(props: AvatarProps & { size: Size })",
             "documented_sig": AVATAR_CONSTANT["usage_signature"], "issue": "leaves out the required prop 'size'"}]},
        {"file": "src/badge.tsx", "signature_mismatches": [
            {"name": "badgeVariants", "line": 3, "source_sig": "cva(...)", "documented_sig": "badgeVariants",
             "issue": "a data constant"}]},
    ]))
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--results", results).stdout)
    assert out["comparedNames"] == ["Avatar", "Tabs"]
    assert [(g["export"], g["severity"]) for g in out["gapRecords"]] == [("Avatar", "Critical")]
    assert any("`badgeVariants`, which is no documented signature" in w for w in out["warnings"])


@pytest.mark.parametrize("payload, needle", [
    ("not json", "not valid JSON"),
    ({"signature_mismatches": []}, "`file` must be a non-empty string"),
    ({"file": "a.ts"}, "`signature_mismatches` must be present"),
    ({"file": "a.ts", "signature_mismatches": [{"name": "x"}]}, "missing field(s)"),
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "line": "1"}]}, "`line` must be a line number"),
    ({"file": "a.ts", "exports_found": "x", "signature_mismatches": []}, "`exports_found` must be a list"),
    # #793: a difference outside the enum is refused, the field named
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "difference": "bogus"}]},
     'signature_mismatches[0]: `difference` must be one of parameter-name, omitted-optional, annotation-contradicted '
     'when present, not "bogus"'),
    # #835: an annotation-contradicted mismatch names the body line that returns the documented type, and only it
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "difference": "annotation-contradicted"}]},
     "signature_mismatches[0]: `evidence_line` must be a line number (an integer from 1) with `difference` "
     "annotation-contradicted, not null"),
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "difference": "annotation-contradicted",
                                                "evidence_line": "19"}]},
     '`evidence_line` must be a line number (an integer from 1) with `difference` annotation-contradicted, not "19"'),
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "difference": "annotation-contradicted",
                                                "evidence_line": 0}]},
     "`evidence_line` must be a line number (an integer from 1) with `difference` annotation-contradicted, not 0"),
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "difference": "annotation-contradicted",
                                                "evidence_line": True}]},
     "`evidence_line` must be a line number (an integer from 1) with `difference` annotation-contradicted, not true"),
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "difference": "omitted-optional", "evidence_line": 19}]},
     'signature_mismatches[0]: `evidence_line` is given only with `difference` annotation-contradicted, '
     'not "omitted-optional"'),
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "evidence_line": 19}]},
     "`evidence_line` is given only with `difference` annotation-contradicted, not null"),
    # #781: a mismatch's candidate `file`, when given, is a path
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "file": ""}]},
     'signature_mismatches[0]: `file` must be a non-empty string when present, not ""'),
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "file": 3}]},
     "signature_mismatches[0]: `file` must be a non-empty string when present, not 3"),
    # #826: a mismatch's `form`, when given, is the index of the documented form it was graded against
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "form": "1"}]},
     'signature_mismatches[0]: `form` must be an index (an integer from 0) when present, not "1"'),
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "form": -1}]},
     "signature_mismatches[0]: `form` must be an index (an integer from 0) when present, not -1"),
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "form": True}]},
     "signature_mismatches[0]: `form` must be an index (an integer from 0) when present, not true"),
], ids=["not-json", "no-file", "no-mismatches", "missing-fields", "line-not-int", "exports-not-list",
        "bad-difference", "contradicted-without-evidence-line", "evidence-line-not-int", "evidence-line-zero",
        "evidence-line-bool", "evidence-line-on-another-tag", "evidence-line-untagged", "empty-mismatch-file",
        "mismatch-file-not-a-string", "form-not-int", "form-negative", "form-bool"])
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
