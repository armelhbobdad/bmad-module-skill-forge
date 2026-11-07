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
    for no change to the skill, else a Critical one with a warning that
    says why; the script checks that both signatures write the same
    parameters as the comparison rules read them (6.0.0 release gate): a
    `def` keyword, a decorator, a Go receiver, a leading `self` the source
    writes, a type only one side writes or a common equivalent spelling of
    one, a default's value and
    the names of `*args` and `**kwargs` never refuse the tag, a list of bare
    names or one with an ellipsis need not write every parameter, while a
    name, the order, a type both write, an optionality the documented list
    states, type parameters both write, a TS/JS literal default's type and a
    caller's shifted positions do
  - plans each check at the declaration the skill cites (#781): for a name
    the surface records in several files, `plan --skill-dir` picks the one
    file the skill cites on a line naming it, and hands the judge every
    file as `candidates` when the citations do not settle it; a record with
    no file never wins, and a mismatch found at a candidate names its `file`;
    end to end (#830), the runner and the surface give a name two monorepo
    packages define one record per file, so the cited one is compared
  - binds a documented form to the one declaration of its name its own
    citations name (#918), read at the place the inventory's `at` gives: a
    surface record, or a same-named declaration no entry point exports (the
    surface's `otherDeclarations`); the judge compares a bound form with it
    alone and score takes its mismatch there, while a form bound to nothing
    is planned as before and a plan with no binding is byte for byte the
    one before; such a declaration is never the planned record or a
    candidate, and joins no name, set or count; a neighbouring line that is
    another place of the name never lends a form its citations
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
    # a parameter difference is no annotation the body contradicts: a type both sides write
    ({**CONTRADICTED, "documented_sig": "(port: str = 8001) -> Callable[[], None]"}, VIZ_TEXT, {},
     "its parameters differ: documented `(port: str = 8001)`, source `(port: int = 8001)`"),
    # ... the count, a name, an optionality the documented list states, a name after a `*` marker
    ({**CONTRADICTED, "documented_sig": "(a, b) -> X", "source_sig": "(a) -> Y"}, VIZ_TEXT, {},
     "its parameters differ: documented `(a, b)`, source `(a)`"),
    ({**CONTRADICTED, "documented_sig": "(a, c) -> X", "source_sig": "(a, b) -> Y"}, VIZ_TEXT, {},
     "its parameters differ: documented `(a, c)`, source `(a, b)`"),
    ({**CONTRADICTED, "documented_sig": "(a, b=1) -> X", "source_sig": "(a=0, b=1) -> Y"}, VIZ_TEXT, {},
     "its parameters differ: documented `(a, b=1)`, source `(a=0, b=1)`: parameter 1: `a` is required in the "
     "documented list, optional in the source"),
    ({**CONTRADICTED, "documented_sig": "(width: int, height: int) -> X",
      "source_sig": "def f(height: int, width: int) -> Y"}, VIZ_TEXT, {},
     "its parameters differ: documented `(width: int, height: int)`, source `def f(height: int, width: int)`: "
     "parameter 1 is `width` in the documented list, `height` in the source"),
    ({**CONTRADICTED, "documented_sig": "(a, *, c, b) -> X", "source_sig": "(a, *, b, d) -> Y"}, VIZ_TEXT, {},
     "its parameters differ: documented `(a, *, c, b)`, source `(a, *, b, d)`"),
    # a signature with no parameter group keeps the text comparison
    ({**CONTRADICTED, "documented_sig": "make -> X", "source_sig": "make() -> Y"}, VIZ_TEXT, {},
     "its parameters differ: documented `make`, source `make()`: the documented signature has no parameter group"),
    # a documented entry that states no return type claims none, so nothing contradicts it
    ({**CONTRADICTED, "documented_sig": "(port: int = 8001)"}, VIZ_TEXT,
     {"entry": {k: v for k, v in VIZ.items() if k != "return_type"}},
     "the documented signature states no return type"),
    # ... nor does one whose return names values (#957), after the arrow or in `return_type`
    ({**CONTRADICTED, "documented_sig": "(port: int = 8001) → (server, stop)"}, VIZ_TEXT,
     {"entry": {k: v for k, v in VIZ.items() if k != "return_type"}},
     "the documented signature states no return type"),
    ({**CONTRADICTED, "documented_sig": "(port: int = 8001) → [server, stop]"}, VIZ_TEXT,
     {"entry": {k: v for k, v in VIZ.items() if k != "return_type"}},
     "the documented signature states no return type"),
    ({**CONTRADICTED, "documented_sig": "(port: int = 8001)"}, VIZ_TEXT,
     {"entry": {**VIZ, "return_type": "(server, stop)"}},
     "the documented signature states no return type"),
], ids=["line-not-a-return", "line-before-the-declaration", "the-declaration-line", "past-the-end", "no-such-file",
        "a-comment", "a-return-in-a-later-function", "a-parameter-difference", "a-parameter-count", "a-parameter-name",
        "an-optionality-the-list-states", "typed-parameters-swapped", "a-name-after-a-star-marker",
        "no-parameter-group", "no-documented-return-type", "a-value-name-list", "a-bracketed-value-name-list",
        "a-value-name-return-type"])
def test_a_contradiction_whose_facts_do_not_check_is_critical(tmp_path, mismatch, text, kwargs, fact):
    """The tag alone never lowers a grade: a documented entry with no return type (none at all, or, #957, a list of
    value names after the arrow or in `return_type`), a parameter difference the rules compare (a type both sides
    write, the count, a name, an optionality the documented list states, or, for a signature with no parameter
    group, its text before the return), an evidence line before the declaration or past the next one, or, with
    --source-root, one that does not start with `return` (a comment does not) or that the file lacks, is graded as
    an untagged mismatch, and a warning names the fact that failed (for the parameters, both texts before the
    return and why they differ) at the declaration's line."""
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


@pytest.mark.parametrize("text, extension, states", [
    ("(nodes, edges)", ".py", False), ("(nodes)", ".py", False), ("[state, setState]", ".ts", False),
    ("{ data, error }", ".tsx", False),
    ("str", ".py", True), ("(str, int)", ".py", True), ("(int, error)", ".go", True), ("[string, number]", ".ts", True),
    ("result", ".py", True), ("(nodes: list[Node], edges)", ".py", True), ("HTML str", ".py", True),
    ("[S, Dispatch<SetStateAction<S>>]", ".ts", True), ("{ data: T; error: E }", ".ts", True),
    ("(a, b)[0]", ".py", True),
    ("(usize, usize)", ".rs", True), ("(boolean, boolean)", ".java", True), ("(data, error)", ".java", False),
    ("(decimal, decimal)", ".cs", True),
    # a TS/JS table also reads the script of a .vue, .svelte or .astro file, where Go's `error` names a value
    ("{ data, error }", ".vue", False),
    # a file of a language with no table, or none, checks every table: Go's `error` keeps the list a stated return
    ("{ data, error }", "", True), ("{ data, error }", ".kt", True),
    ("", ".py", False), ("   ", ".py", False), (None, ".py", False), (["nodes", "edges"], ".py", False),
], ids=["parenthesized-names", "one-name-in-parentheses", "bracketed-names", "braced-names", "a-type", "a-type-list",
        "a-go-result-list", "a-ts-tuple", "a-single-name", "a-typed-name-among-names", "a-description-and-a-type",
        "a-generic-tuple", "an-object-type-literal", "an-indexed-list", "a-rust-tuple", "a-c-family-list",
        "a-go-type-name-in-a-c-family-file", "a-cs-tuple", "a-vue-file", "no-file", "a-language-with-no-table",
        "blank", "whitespace", "none", "not-text"])
def test_a_return_written_as_value_names_states_none(text, extension, states):
    """#957: signature-comparison-rules.md (Annotations) reads a parenthesized, bracketed or braced list of value
    names as no return type, and so does the script: a list reads as names of values only when each item is a bare
    name that starts lowercase and is no builtin type name of the file's language (every language's, for a file of
    none). A type alone or in a list, a single name, a list that writes a type among its names, a description
    followed by a type and any other text state one; a blank return, or no text, states none, as before."""
    assert mod._states_return(text, extension) is states


@pytest.mark.parametrize("documented_sig", [
    "(port: int = 8001) -> (str, int)", "(port: int = 8001) -> result",
    "(port: int = 8001) -> (nodes: list[Node], edges)", "(port: int = 8001) -> HTML str",
], ids=["a-type-list", "a-single-name", "a-typed-name-among-names", "a-description-and-a-type"])
def test_a_contradiction_whose_return_writes_a_type_keeps_its_facts(tmp_path, documented_sig):
    """#957: a return that writes a type (or a single name) still states one, so with no `return_type` the
    contradiction's facts check and `score` grades it Info, with no warning, as before."""
    mismatch = {**CONTRADICTED, "documented_sig": documented_sig}
    assert mod.contradiction_fact(mismatch, {}, VIZ_FILE, 12) is None
    proc, _ = _contradiction_run(tmp_path, mismatch, entry={k: v for k, v in VIZ.items() if k != "return_type"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert [(m["difference"], m["severity"]) for m in out["mismatches"]] == [("annotation-contradicted", "Info")]
    assert not any("annotation-contradicted" in w for w in out["warnings"]), out["warnings"]


@pytest.mark.parametrize("documented_sig, source_sig, file, severity", [
    ("(key: string) => { data, error }", "(key: string) => Promise<X>", "src/use-fetch.tsx", "Critical"),
    ("(init: S): [state, setState]", "(init: S): [S, Dispatch<SetStateAction<S>>]", "src/use-state.ts", "Critical"),
    ("(init: S): [string, number]", "(init: S): [S, number]", "src/use-state.ts", "Info"),
    ("Start(port int) (int, error)", "Start(port int) error", "pkg/s.go", "Info"),
], ids=["a-braced-list-in-a-tsx-file", "a-bracketed-list-in-a-ts-file", "a-ts-tuple", "a-go-result-list"])
def test_the_mismatch_s_file_says_how_its_language_reads_a_return(tmp_path, documented_sig, source_sig, file,
                                                                  severity):
    """#957, end to end: the file a mismatch is reported at gives the return check its language. In a TS file a
    braced or bracketed list of value names states no return type, so the tag is refused and the mismatch is
    Critical, while a list of the language's types (`[string, number]`, Go's `(int, error)`) states one and stays
    an Info observation."""
    record = {**VIZ_SURFACE["exports"][0], "file": file}
    proc, _ = _contradiction_run(tmp_path, {**CONTRADICTED, "documented_sig": documented_sig, "source_sig": source_sig},
                                 surface_records=[record], file=file,
                                 entry={k: v for k, v in VIZ.items() if k != "return_type"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert [m["severity"] for m in out["mismatches"]] == [severity], out["warnings"]
    if severity == "Critical":
        assert any("the documented signature states no return type" in w and "(Critical)" in w
                   for w in out["warnings"]), out["warnings"]
    else:
        assert not any("annotation-contradicted" in w for w in out["warnings"]), out["warnings"]


def test_a_return_stated_in_either_place_keeps_a_contradiction_s_facts():
    """#957: the documented entry states a return type when its `return_type` or its signature's return does, so a
    list of value names in one place and a type in the other keeps the facts. `return_type` is read in the file's
    language too: in a TSX file `{ data, error }` there names values."""
    assert mod.contradiction_fact({**CONTRADICTED, "documented_sig": "(port: int = 8001) -> (str, int)"},
                                  {"return_type": "(server, stop)"}, VIZ_FILE, 12) is None
    assert mod.contradiction_fact({**CONTRADICTED, "documented_sig": "(port: int = 8001) -> (server, stop)"},
                                  {"return_type": "Server"}, VIZ_FILE, 12) is None
    assert mod.contradiction_fact({**CONTRADICTED, "documented_sig": "(key: string)",
                                   "source_sig": "(key: string) => Promise<X>"}, {"return_type": "{ data, error }"},
                                  "src/use-fetch.tsx", 12) == "the documented signature states no return type"


RUN_PARALLEL_FILE ="cognee/modules/pipelines/operations/run_parallel.py"
RUN_PARALLEL_LINES = [f"# line {n}" for n in range(1, 20)]
RUN_PARALLEL_LINES[7] = "def run_tasks_parallel(tasks: list[Task]) -> Callable[[Any], Generator[Any, Any, Any]]:"
RUN_PARALLEL_LINES[14] = "    return Task(parallel_run)"
# The 6.0.0 release gate's two contradictions (oms-cognee), their signatures as the judges wrote them.
RELEASE_GATE = {
    "visualization_server": (
        {**CONTRADICTED, "documented_sig": "visualization_server(port) -> shutdown() callable",
         "source_sig": "def visualization_server(port) -> Callable[[], Callable[[], None]]"},
        VIZ_TEXT, {}),
    "run_tasks_parallel": (
        {"name": "run_tasks_parallel", "line": 8, "documented_sig": "run_tasks_parallel(tasks) -> Task",
         "source_sig": "def run_tasks_parallel(tasks: list[Task]) -> Callable[[Any], Generator[Any, Any, Any]]",
         "issue": "the declaration annotates a Callable; the body returns Task(parallel_run)",
         "difference": "annotation-contradicted", "evidence_line": 15},
        "\n".join(RUN_PARALLEL_LINES) + "\n",
        {"entry": {"name": "run_tasks_parallel", "kind": "function", "params": "tasks", "return_type": "Task"},
         "surface_records": [{"name": "run_tasks_parallel", "kind": "function", "file": RUN_PARALLEL_FILE, "line": 8,
                              "signatureLine": RUN_PARALLEL_LINES[7], "origin": "extraction"}],
         "file": RUN_PARALLEL_FILE}),
}


@pytest.mark.parametrize("name", list(RELEASE_GATE))
def test_the_release_gate_contradictions_are_info_observations(tmp_path, name):
    """6.0.0 release gate (oms-cognee): the judge tagged both annotations correctly, and `score` refused each tag
    because the two texts before the return differed where the rules compare nothing, a `def` keyword before
    `visualization_server(port)` and a type (`list[Task]`) the documented `run_tasks_parallel(tasks)` does not
    write. The parameters are compared as the rules read them, so each is an Info observation that still
    matches, and the gate passes."""
    mismatch, text, kwargs = RELEASE_GATE[name]
    proc, gaps = _contradiction_run(tmp_path, mismatch, text, **kwargs)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert [(m["name"], m["severity"]) for m in out["mismatches"]] == [(name, "Info")], out["warnings"]
    assert (out["matchingSignatures"], out["signatureAccuracy"]) == (1, 100.0)
    assert not any("annotation-contradicted" in w for w in out["warnings"]), out["warnings"]
    assert [g["title"] for g in json.loads(gaps.read_text(encoding="utf-8"))] == [f"Annotation contradicted: {name}"]
    gate = _append_and_gate(tmp_path, gaps)
    assert (gate["gate"], gate["counts"]["Critical"]) == ("passed", 0)


@pytest.mark.parametrize("documented_sig, source_sig", [
    ("(a, b) -> X", "(a, b=1) -> Y"),
    ("async def f(self, a: typing.List[int]) -> X", "def f(self, a: List[int]) -> Y"),
    ("(*args, **kw) -> X", "(*items, **options) -> Y"),
    ("(a, *, c, b) -> X", "(a, *, b, c) -> Y"),
    ("(cb: (x: A, y: B) => void, n: Record<string, number>) => X",
     "(cb: (x: A, y: B) => void, n: Record<string, number>) => Y"),
    ("(cb, n) => X", "(cb: (x: A, y: B) => void, n: Record<string, number>) => Y"),
    ("(port: int = 9000) -> X", "(port: int = 8001) -> Y"),
    ("(a, b) -> X", "(a, b, /) -> Y"),
    ("make -> X", "make -> Y"),
], ids=["no-optionality-stated", "a-keyword-self-and-a-typing-prefix", "the-names-of-args-and-kwargs",
        "by-name-after-a-star-marker", "commas-inside-nested-brackets-and-arrows", "a-type-only-the-source-writes",
        "a-default-s-value", "a-positional-only-marker", "no-parameter-group-and-the-same-text"])
def test_what_the_rules_leave_uncompared_never_refuses_a_contradiction(tmp_path, documented_sig, source_sig):
    """`documented_sig` and `source_sig` write the same parameters as signature-comparison-rules.md reads them, not
    as text: an optionality the documented list states for no member, a `def` or `async def` keyword before the
    group, a leading `self` both sides write, a `typing.` prefix, the names of `*args` and `**kwargs`, the order
    after a `*` marker, a type only one side writes, a default's value and a `/` marker are never compared, and a
    comma inside a callback's parameters or a type's arguments splits no parameter. A signature with no parameter
    group agrees by its text before the return. Each is an Info observation."""
    proc, _ = _contradiction_run(tmp_path, {**CONTRADICTED, "documented_sig": documented_sig,
                                            "source_sig": source_sig})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert [m["severity"] for m in out["mismatches"]] == ["Info"], out["warnings"]


@pytest.mark.parametrize("documented_sig, source_sig, file, severity", [
    ("(pageSize?: string) => X", "(pageSize = 20) => Y", "src/table.ts", "Critical"),
    ("(pageSize?: number) => X", "(pageSize = 20) => Y", "src/table.ts", "Info"),
    ("(str, end) => X", "(str: string, start?: number, end?: number) => Y", "src/slice.ts", "Critical"),
    ("(s, end) -> X", "(s: str, start: int = 0, end: int = -1) -> Y", "pkg/slice.py", "Info"),
], ids=["a-ts-literal-default-s-type", "the-same-ts-literal-type", "a-ts-positional-shift", "no-shift-in-python"])
def test_the_mismatch_s_file_says_how_its_language_reads_the_parameters(tmp_path, documented_sig, source_sig, file,
                                                                       severity):
    """End to end, the file a mismatch is reported at gives contradiction_fact its language: in a TS/JS file a
    source parameter with no type and a literal default has that literal's type, and a list of bare names that
    leaves out an optional parameter before one it writes shifts a caller's positions, which Python's keyword
    arguments do not."""
    record = {**VIZ_SURFACE["exports"][0], "file": file}
    proc, _ = _contradiction_run(tmp_path, {**CONTRADICTED, "documented_sig": documented_sig, "source_sig": source_sig},
                                 surface_records=[record], file=file)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert [m["severity"] for m in out["mismatches"]] == [severity], out["warnings"]


def _parameter_fact(documented_sig: str, source_sig: str, extension: str = ".py") -> str | None:
    """contradiction_fact for a mismatch at a file of `extension` whose facts other than its parameters check."""
    entry = {"documented_sig": documented_sig, "source_sig": source_sig, "evidence_line": 19}
    return mod.contradiction_fact(entry, {"return_type": "X"}, f"src/viz{extension}", 12)


def _check_parameters(documented_sig: str, source_sig: str, extension: str, reason: str | None) -> None:
    """The parameter fact agrees (`reason` None), or refuses with today's prefix and then `reason`."""
    fact = _parameter_fact(documented_sig, source_sig, extension)
    if reason is None:
        assert fact is None, fact
    else:
        assert fact is not None and fact.startswith("its parameters differ: documented `") and reason in fact, fact


@pytest.mark.parametrize("sig, extension, parameters", [
    ("(path, size=1 << 20, mode)", ".py",
     [("path", "", False, False), ("size", "", True, False), ("mode", "", False, False)]),
    ("def f(a=x<3, b=1)", ".py", [("a", "", True, False), ("b", "", True, False)]),
    ("def f(a: int = 0 if n < 2 else 1, b: int = 2)", ".py", [("a", "int", True, False), ("b", "int", True, False)]),
    ("def f(a=g(x < 3), b=1) -> X", ".py", [("a", "", True, False), ("b", "", True, False)]),
    ("(a: boolean = x < y, b: Map<string, number>)", ".ts",
     [("a", "boolean", True, False), ("b", "Map<string,number>", False, False)]),
    ("(m: Map<string, number>, n)", ".ts", [("m", "Map<string,number>", False, False), ("n", "", False, False)]),
    ("(m: Map<(k: K) => V, string>, n: number) => X", ".ts",
     [("m", "Map<(k:K)=>V,string>", False, False), ("n", "number", False, False)]),
    ("(cb: (x: A, y: B) => void, n: Record<string, number>, sep: str = \", \") => X", ".ts",
     [("cb", "(x:A,y:B)=>void", False, False), ("n", "Record<string,number>", False, False),
      ("sep", "str", True, False)]),
    ("(props: Omit<P, 'on-change'>, n: number) => X", ".ts",
     [("props", "Omit<P,'on-change'>", False, False), ("n", "number", False, False)]),
    ("(props: Omit<P, 'a,b'>, n: number) => X", ".ts",
     [("props", "Omit<P,'a,b'>", False, False), ("n", "number", False, False)]),
    ("(r: Record<'on off', number>, n: number) => X", ".ts",
     [("r", "Record<'on off',number>", False, False), ("n", "number", False, False)]),
    ("fn f<'a>(x: &'a str, t: impl Tr + 'a) -> &'a str", ".rs",
     [("x", "&'a str", False, False), ("t", "impl Tr+'a", False, False)]),
    ("export function f<T extends (a: X, b: Y) => Z>(x: T, y?: number): T", ".ts",
     [("x", "T", False, False), ("y", "number", True, False)]),
    ("def f(cls, a: typing.Optional[int] = None, *args, key, **kw) -> X", ".py",
     [("cls", "", False, False), ("a", "typing.Optional[int]", True, False), ("*", "", False, False),
      ("key", "", False, True), ("**", "", False, True)]),
    ("def f(a, /, b, *, c, d=1)", ".py", [("a", "", False, False), ("b", "", False, False), ("c", "", False, True),
                                          ("d", "", True, True)]),
], ids=["a-shift-operator", "a-less-than", "a-conditional-default", "a-less-than-inside-a-call",
        "a-less-than-after-a-space", "a-generic-s-comma", "a-callback-inside-a-generic",
        "nested-commas-and-a-string-default", "a-string-literal-type", "a-string-literal-with-a-comma",
        "a-string-literal-with-a-space", "rust-lifetimes", "type-parameters-before-the-group",
        "a-leading-cls-and-star-parameters", "the-markers"])
def test_a_parameter_list_is_split_at_its_top_level_commas(sig, extension, parameters):
    """The group splits only at a comma outside every bracket pair and string: a callback's parameters, a type's
    arguments or a default's string stays one parameter. A `<` opens a pair only when it follows a name, a `.`, a
    `]` or a `>` with no space between and a `>` closes it before the pair around it does, so a shift, a
    less-than or a conditional in a default nests nothing; an arrow's `>` closes no `<`; a `'` opens a string
    (`'on-change'`, `'a,b'`, `'on off'`) unless it is a Rust lifetime in a `.rs` file (`&'a`, `+ 'a`). Each
    parameter is its key (`*` and `**` for any `*args` and `**kwargs`), the type it writes, compacted, whether a
    default or a `?` marks it optional, and whether it comes after a `*` marker, a bare `*` or `*args`; a `/` and
    a bare `*` are none, and a leading `cls` is kept, as a receiver."""
    params = mod._parameters(sig, extension)
    assert [(p["key"], p["type"], p["optional"], p["by_name"]) for p in params] == parameters
    assert [p["receiver"] for p in params] == [p[0] == "cls" for p in parameters]


def test_a_rust_lifetime_is_read_only_in_a_rust_file():
    """A `'` starts a lifetime only in a `.rs` file: anywhere else it opens a string, which here runs to the end,
    so the group never closes and the signature has no parameter list."""
    sig = "fn f<'a>(x: &'a str, n: usize) -> X"
    assert [p["key"] for p in mod._parameters(sig, ".rs")] == ["x", "n"]
    assert mod._parameters(sig, ".py") is None and mod._parameters(sig, ".ts") is None


@pytest.mark.parametrize("sig", ["make -> X", "make -> f(x)", "f(a, b", "<Canvas of={X} />"],
                         ids=["no-parentheses", "parentheses-after-the-return-arrow", "a-group-that-does-not-close",
                              "a-component-usage"])
def test_a_signature_with_no_parameter_group_is_compared_as_text(sig):
    """No `(` before the return arrow, or a group that does not close, is no parameter list: contradiction_fact
    compares such a signature by its text before the return, and says which side has no group."""
    assert mod._parameters(sig) is None
    _check_parameters(sig, "make() -> Y", ".py", "the documented signature has no parameter group, so the texts "
                                                 "before the return are compared")
    _check_parameters("make() -> X", sig, ".py", "the source signature has no parameter group")


@pytest.mark.parametrize("sig", [
    "each with x=A(); f(a, b) -> X",
    "f(a: int) -> X; f(a: str) -> X",
    "useA(x); useA(x, y)",
])
def test_a_semicolon_joined_text_has_no_parameter_list(sig):
    """A `;` outside every bracket pair and string (shared text before a name's own members, an overload set or a
    usage list) leaves no parameter list to read, so its first group, which may be a call inside the shared text,
    is never compared as the parameters: the texts before the return decide, and a refusal says so."""
    assert mod._parameters(sig) is None
    _check_parameters(sig, "def f() -> Y", ".py", "the documented signature has no parameter group")
    assert mod._parameters("(a: { x: number; y: string }, b) => X", ".ts") is not None


@pytest.mark.parametrize("documented_sig, source_sig, reason", [
    ("make -> X", "build -> Y", "neither signature has a parameter group"),
    ("make -> X", "make -> Y", None),
], ids=["different-texts", "the-same-text"])
def test_two_signatures_with_no_parameter_group_are_compared_as_text(documented_sig, source_sig, reason):
    """When neither side has a parameter group, the texts before the return decide, and a refusal says so."""
    _check_parameters(documented_sig, source_sig, ".py", reason)


@pytest.mark.parametrize("sig, keys", [
    ("func (s *Server) Start(port string, x int) error", ["port string", "x int"]),
    ("func Start(port int) (int, error)", ["port int"]),
    ("@lru_cache(maxsize=None) def f(x)", ["x"]),
    ('@Annotation(value="x") public void f(int x)', ["int x"]),
    ("R operator()(int x) const", ["int x"]),
    ("void f(int x) noexcept(true)", ["int x"]),
    ("void f(int x) throw()", ["int x"]),
    ("void f(int x) __attribute__((nonnull))", ["int x"]),
    ("template<class T> void f(T x) requires(Small<T>)", ["T x"]),
    ("auto f(int x) decltype(g(x))", ["int x"]),
], ids=["a-go-receiver", "a-go-result-list", "a-decorator", "a-java-annotation", "a-cpp-call-operator",
        "noexcept", "throw", "attribute", "requires", "decltype"])
def test_the_parameter_group_is_no_prefix_group(sig, keys):
    """The parameter group is the first top-level group that a decorator or a Java annotation does not write (no
    `@name` before it) and that no other `(` follows directly, nor a name and a `(` after whitespace: a Go
    receiver, a decorator's arguments and C++'s `operator()` are passed over, while a Go result list after a space
    is the return, and a C or C++ qualifier that takes arguments (`noexcept`, `throw`, `__attribute__`, `requires`,
    `decltype`) leaves the group before it the parameter group."""
    assert [p["key"] for p in mod._parameters(sig)] == keys


@pytest.mark.parametrize("documented_sig, source_sig, extension, reason", [
    ("func (s *Server) Start(port string, x int) error", "func (s *Server) Start(port int) error", ".go",
     "`port string` is not a source parameter"),
    ("Start(port int) -> error", "func (s *Server) Start(port int) error", ".go", None),
    ("Start(port int) -> (int, error)", "func Start(port int) (int, error)", ".go", None),
    ("f(x) -> X", "@lru_cache(maxsize=None) def f(x) -> Y", ".py", None),
    ("f(x, y) -> X", "@lru_cache(maxsize=None) def f(x) -> Y", ".py", "`y` is not a source parameter"),
    ("operator()(int x) -> R", "R operator()(int x) const", ".cpp", None),
    ("operator()(int x, int y) -> R", "R operator()(int x) const", ".cpp", "`int y` is not a source parameter"),
    ("f(int x) -> void", '@Annotation(value="x") public void f(int x)', ".java", None),
    ("f(int x) -> void", "void f(int y) noexcept(true)", ".cpp", "`int x` is not a source parameter"),
    ("f(int x) -> void", "void f(int x) noexcept(true)", ".cpp", None),
], ids=["a-go-receiver-s-method-refuses", "a-go-receiver-s-method-agrees", "a-go-result-list", "a-decorator-agrees",
        "a-decorator-refuses", "a-cpp-call-operator-agrees", "a-cpp-call-operator-refuses", "a-java-annotation",
        "a-qualifier-keeps-the-group-and-refuses", "a-qualifier-keeps-the-group-and-agrees"])
def test_a_prefix_group_is_never_compared_as_the_parameters(documented_sig, source_sig, extension, reason):
    """A Go receiver, a decorator's or annotation's arguments and C++'s `operator()` are never the parameters,
    so a method whose parameters differ refuses the tag even when both write one receiver, and one whose
    parameters agree keeps it whatever writes the prefix."""
    _check_parameters(documented_sig, source_sig, extension, reason)


@pytest.mark.parametrize("documented_sig, source_sig, reason", [
    ("f<T extends string>(x: T) => X", "f<T extends number>(x: T) => Y",
     "the type parameters differ: documented `T extends string`, source `T extends number`"),
    ("f<T extends string>(x: T) => X", "function f<T extends string>(x: T): Y", None),
    ("f(x: T) => X", "function f<T>(x: T): Y", None),
    ("<T,>(x: T) => X", "<T>(x: T) => Y", None),
    ("def f[T: int](x: T) -> X", "def f[T: str](x: T) -> Y", "the type parameters differ"),
], ids=["a-different-constraint", "the-same-type-parameters", "only-the-source-writes-them", "a-trailing-comma",
        "python-type-parameters"])
def test_type_parameters_both_sides_write_are_compared(documented_sig, source_sig, reason):
    """Type parameters between the name and the group (`<...>`, Python's `[...]`) are compared, compacted and
    without a trailing comma, when both sides write them, and not when only one does."""
    _check_parameters(documented_sig, source_sig, ".ts", reason)


@pytest.mark.parametrize("sig, parts", [
    ("export function f<T extends (a: X) => Z>(x: T)", ("export function f<T extends (a: X) => Z>(x: T)", "")),
    ("func Start(port int) (int, error)", ("func Start(port int)", "(int, error)")),
    ("func (s *Server) Start(port int) error", ("func (s *Server) Start(port int)", "error")),
    ("make -> X", ("make", "X")),
], ids=["a-group-inside-type-parameters", "a-go-result-list", "a-go-receiver", "no-group"])
def test_the_head_and_the_return_are_read_from_the_parameter_group(sig, parts):
    """_signature_parts reads the head and the return from the group _parameters reads, so a `(` inside type
    parameters is not the group and a refusal quotes the head that was compared."""
    assert mod._signature_parts(sig) == parts


def test_a_group_inside_type_parameters_states_no_return_type():
    """A `(` inside the type parameters is no group, so a form with no return after its group states none, and a
    refusal quotes each head up to the group's `)`."""
    entry = {"documented_sig": "export function f<T extends (a: X) => Z>(x: T)",
             "source_sig": "export function f<T extends (a: X) => Z>(x: T): Z", "evidence_line": 19}
    assert mod.contradiction_fact(entry, {}, "src/f.ts", 12) == "the documented signature states no return type"
    _check_parameters("f<T extends (a: X) => Z>(x: T) => R", "f<T extends (a: X) => Z>(x: T, y: U) => R", ".ts",
                      "documented `f<T extends (a: X) => Z>(x: T)`, source `f<T extends (a: X) => Z>(x: T, y: U)`: "
                      "the documented list writes 1 parameter, the source 2")


@pytest.mark.parametrize("documented_sig, source_sig, reason", [
    ("(a: typing.Any) -> X", "(a: Any) -> Y", None),
    ("(a: collections.abc.Sequence[int]) -> X", "(a: Sequence[int]) -> Y", None),
    ("(children: ReactNode) => X", "(children: React.ReactNode) => Y", None),
    ("(a: typing_extensions.Self) -> X", "(a: Self) -> Y", "`a` is typed `typing_extensions.Self`"),
    ("(a: Optional[int]) -> X", "(a: int | None) -> Y", None),
    ("(a: Union[int, None]) -> X", "(a: int | None) -> Y", None),
    ("(a: Optional[int]) -> X", "(a: str | None) -> Y", "`a` is typed `Optional[int]`"),
    ("(a: Union[A, B]) -> X", "(a: A | B) -> Y", None),
    ("(a: B | A) -> X", "(a: A | B) -> Y", None),
    ("(a: List[int]) -> X", "(a: list[int]) -> Y", None),
    ("(a: Dict[str, int]) -> X", "(a: dict[str, int]) -> Y", None),
    ("(a: Tuple[int, str]) -> X", "(a: tuple[int, str]) -> Y", None),
    ("(a: Set[int]) -> X", "(a: set[int]) -> Y", None),
    ("(a: FrozenSet[int]) -> X", "(a: frozenset[int]) -> Y", None),
    ("(a: Type[T]) -> X", "(a: type[T]) -> Y", None),
    ("(a: List[int]) -> X", "(a: list[str]) -> Y", "`a` is typed `List[int]`"),
    ("(a: Dict) -> X", "(a: dict) -> Y", None),
    ("(a: (int | None)) -> X", "(a: int | None) -> Y", None),
    ('(a: "Node") -> X', "(a: Node) -> Y", None),
    ("(a: Array<T>) => X", "(a: T[]) => Y", None),
    ("(a: ReadonlyArray<T>) => X", "(a: readonly T[]) => Y", None),
    ("(a: Array<T>) => X", "(a: readonly T[]) => Y", "`a` is typed `Array<T>`"),
    ("(a: dict) -> X", "(a: dict[str, Any]) -> Y", None),
    ("(a: dict[str, Any]) -> X", "(a: dict) -> Y", None),
    ("(a: list[dict]) -> X", "(a: list[dict[str, Any]]) -> Y", None),
    ("(a: dict[str, int]) -> X", "(a: dict[str, str]) -> Y", "`a` is typed `dict[str,int]`"),
    ("(schema: VectorSchemaProvider) -> X", "(schema: VectorSchemaProvider | MultiVectorSchemaProvider) -> Y", None),
    ("(schema: A | B) -> X", "(schema: A) -> Y", "`schema` is typed `A|B` in the documented list, `A` in the source"),
    ("(a: T) -> X", "(a: U) -> Y", "`a` is typed `T` in the documented list, `U` in the source"),
], ids=["a-typing-prefix", "a-collections-abc-prefix", "a-react-prefix", "a-typing-extensions-prefix-is-compared",
        "optional-and-a-none-union", "union-with-none", "optional-of-another-type", "union-and-a-bar",
        "a-union-in-any-order", "typing-list", "typing-dict", "typing-tuple", "typing-set", "typing-frozenset",
        "typing-type", "a-list-of-another-type", "a-bare-typing-alias", "a-parenthesized-union",
        "a-forward-reference", "array-and-brackets",
        "readonly-array-and-readonly-brackets", "an-array-is-no-readonly-array", "type-arguments-the-form-leaves-out",
        "type-arguments-the-source-leaves-out", "nested-type-arguments-left-out", "type-arguments-both-write-differ",
        "a-documented-member-of-the-source-s-union", "a-documented-union-wider-than-the-source-s",
        "a-renamed-type-variable"])
def test_types_both_sides_write_are_compared_by_the_rules_equivalent_spellings(documented_sig, source_sig, reason):
    """A type both sides write is compared as Equivalent spellings and Annotations read it: a `typing.`,
    `collections.abc.` or `React.` prefix (not `typing_extensions.`), `Optional` and `Union` against `|`, a
    union in any order, `typing`'s aliases against the builtins, a quoted forward reference, `Array<T>` against
    `T[]` and `ReadonlyArray<T>` against `readonly T[]`, and type arguments one side leaves out; a documented type
    that names some of the source's union members agrees, one wider than the source's does not, and a renamed type
    variable stays a difference."""
    _check_parameters(documented_sig, source_sig, ".ts" if "=>" in documented_sig else ".py", reason)


@pytest.mark.parametrize("documented_sig, source_sig, extension, reason", [
    ("(pageSize?: string) => X", "(pageSize = 20) => Y", ".ts",
     "`pageSize` is typed `string` in the documented list, `number` in the source"),
    ("(pageSize?: number) => X", "(pageSize = 20) => Y", ".ts", None),
    ("(sep?: number) => X", '(sep = ", ") => Y', ".js", "`number` in the documented list, `string` in the source"),
    ("(s?: string) => X", "(s = `x${y}`) => Y", ".tsx", None),
    ("(flag?: boolean) => X", "(flag = true) => Y", ".mjs", None),
    ("(n?: bigint) => X", "(n = 123n) => Y", ".ts", None),
    ("(n?: number) => X", "(n = 123n) => Y", ".ts", "`bigint` in the source"),
    ("(page_size: str = 'a') -> X", "(page_size=20) -> Y", ".py", None),
], ids=["a-number-literal-refuses", "a-number-literal-agrees", "a-string-literal", "a-template-literal",
        "a-boolean-literal", "a-bigint-literal", "a-bigint-is-no-number", "no-literal-type-in-python"])
def test_a_ts_js_literal_default_has_its_literal_s_type(documented_sig, source_sig, extension, reason):
    """In a TS/JS file a source parameter with no type and a literal default has that literal's type (a number,
    a string or template literal, a boolean, a bigint), as Annotations says, so a documented type that differs
    from it refuses the tag; in Python a default gives no type."""
    _check_parameters(documented_sig, source_sig, extension, reason)


@pytest.mark.parametrize("documented_sig, source_sig, extension, reason", [
    ("(a) -> X", "(a, b=1) -> Y", ".py", None),
    ("(a) -> X", "(a, b) -> Y", ".py", "the required source parameter `b` is left out"),
    ("(a, b) -> X", "(a) -> Y", ".py", "`b` is not a source parameter"),
    ("(b, a) -> X", "(a, b) -> Y", ".py", "`a` comes before `b` in the source, after it in the documented list"),
    ("(str, end) => X", "(str: string, start?: number, end?: number) => Y", ".ts",
     "the optional `start`, left out before `end`, shifts a caller's positions in a `.ts` file"),
    ("(s, end) -> X", "(s: str, start: int = 0, end: int = -1) -> Y", ".py", None),
    ("(a, b, c) -> X", "(a, *, c, b) -> Y", ".py", None),
    ("(a, *args, c, b) -> X", "(a, *args, b, c) -> Y", ".py", None),
    ("(tasks, data, ...) -> X", "(tasks, data, dataset, user=None) -> Y", ".py", None),
    ("(tasks, …) -> X", "(tasks, data, dataset) -> Y", ".py", None),
    ("(...) -> X", "(tasks, data) -> Y", ".py", None),
    ("(tasks, other, ...) -> X", "(tasks, data, dataset) -> Y", ".py", "`other` is not a source parameter"),
    ("(data, tasks, ...) -> X", "(tasks, data) -> Y", ".py", "`tasks` comes before `data` in the source"),
    ("(tasks: str, ...) -> X", "(tasks: list[Task], data) -> Y", ".py", "`tasks` is typed `str`"),
    ("(...items) => X", "(...rest) => Y", ".ts", "`...items` is not a source parameter"),
    ("(a: int) -> X", "(a: int, b: int = 1) -> Y", ".py", "the documented list writes 1 parameter, the source 2"),
], ids=["bare-names-leave-out-an-optional", "bare-names-leave-out-a-required", "bare-names-write-one-too-many",
        "bare-names-out-of-order", "a-positional-shift-in-ts", "no-positional-shift-in-python",
        "positional-names-against-keyword-only", "by-name-after-args", "an-ellipsis", "a-unicode-ellipsis",
        "an-ellipsis-alone", "an-ellipsis-with-a-name-the-source-lacks", "an-ellipsis-out-of-order",
        "an-ellipsis-with-a-typed-member-that-differs", "a-rest-is-no-ellipsis", "a-typed-list-claims-to-be-complete"])
def test_a_form_that_claims_no_complete_list_need_not_write_every_parameter(documented_sig, source_sig, extension,
                                                                            reason):
    """Reading a form: a list of bare names need not write an optional source parameter, but each name it writes
    must be one, in the source's order (by name alone after a `*` marker), and it may not leave out a required one,
    nor, in a language without keyword arguments, an optional one before a name it writes. A list holding an
    ellipsis claims nothing about what it stands for; the members it writes are still checked. A TS/JS rest is no
    ellipsis, and a list that writes a type, a default or a `?` must write every parameter."""
    _check_parameters(documented_sig, source_sig, extension, reason)


@pytest.mark.parametrize("documented_sig, source_sig, extension, reason", [
    ("get(key) -> X", "def get(self, key) -> Y", ".py", None),
    ("get(self, key) -> X", "def get(self, key) -> Y", ".py", None),
    ("(self, a) -> X", "def f(a) -> Y", ".py", "`self` is not a source parameter"),
    ("(self: Self, a: int) -> X", "def f(a: int) -> Y", ".py", "the documented list writes 2 parameters, the source 1"),
    ("len(&self) -> usize", "fn len(&self) -> usize", ".rs", None),
    ("create(name) -> X", "def create(cls, name) -> Y", ".py", None),
    ("get(key) -> X", "def get(self, key, other) -> Y", ".py", "the required source parameter `other` is left out"),
    ("len() -> usize", "fn len(&self) -> usize", ".rs", None),
    ("push(x: T) -> ()", "fn push(&mut self, x: T)", ".rs", None),
    ("into_inner() -> T", "fn into_inner(mut self) -> T", ".rs", None),
    ("(x: number) => X", "function f(this: Window, x: number): Y", ".ts", None),
], ids=["self", "self-on-both-sides", "a-documented-self-the-source-lacks", "a-typed-documented-self",
        "rust-ref-self-on-both-sides", "cls", "self-and-a-required-parameter-left-out", "rust-ref-self",
        "rust-ref-mut-self", "rust-mut-self", "a-ts-this-parameter"])
def test_a_leading_receiver_is_dropped_where_the_source_writes_one(documented_sig, source_sig, extension, reason):
    """A leading `self`, `cls`, `&self`, `&mut self`, `mut self` or TS `this: T` the source writes is dropped, so a
    method documented without its receiver keeps the tag; the documented list's own is dropped only when the
    source leads with one too, so a documented `self` the source does not take is a parameter it lacks. The
    parameters after it are still compared."""
    _check_parameters(documented_sig, source_sig, extension, reason)


@pytest.mark.parametrize("documented_sig, source_sig, reason", [
    ("(width: int, height: int) -> X", "def f(height: int, width: int) -> Y",
     "parameter 1 is `width` in the documented list, `height` in the source"),
    ("(a: int, *, key: str) -> X", "def f(a: int, *, key: int) -> Y",
     "`key` is typed `str` in the documented list, `int` in the source"),
    ("(a: int, *, kee: int) -> X", "def f(a: int, *, key: int) -> Y",
     "`kee`, written after a `*` marker, is not a source parameter"),
    ("(a: int, b: int, c: int) -> X", "def f(a: int, *, c: int, b: int) -> Y", None),
    ("(a: int, *, b: int, b: int) -> X", "def f(a: int, *, b: int, c: int) -> Y", "a parameter is written twice"),
], ids=["swapped-in-order", "a-keyword-only-type", "a-keyword-only-name", "positional-against-keyword-only",
        "a-name-written-twice"])
def test_a_list_that_claims_to_be_complete_is_paired_in_order_then_by_name(documented_sig, source_sig, reason):
    """A typed list pairs its parameters with the source's in order up to the first either writes after a `*`
    marker, then by name: two typed parameters swapped differ at their position, a keyword-only parameter differs
    by its type or its name, positional parameters pair with keyword-only ones by name, and a name written twice
    after the marker is a difference."""
    _check_parameters(documented_sig, source_sig, ".py", reason)


@pytest.mark.parametrize("documented_sig, source_sig, extension, reason", [
    ("(kind: string) => X", "(kind: 'string') => Y", ".ts",
     "`kind` is typed `string` in the documented list, `'string'` in the source"),
    ('(a: "Node") => X', "(a: Node) => Y", ".ts", '`a` is typed `"Node"`'),
    ('(a: "Node") -> X', "(a: Node) -> Y", ".py", None),
    ("(kind: 'string') => X", "(kind: 'string') => Y", ".ts", None),
], ids=["a-ts-string-literal-type", "a-ts-quoted-type", "a-python-forward-reference", "the-same-literal-type"])
def test_a_quoted_type_is_a_forward_reference_only_outside_ts_js(documented_sig, source_sig, extension, reason):
    """Outside TS/JS a quoted type is a forward reference to the type it quotes; in a TS/JS file it is a string
    literal type, so it differs from the type its text names."""
    _check_parameters(documented_sig, source_sig, extension, reason)


def test_a_less_than_after_a_space_nests_no_parameter():
    """A `<` after a space is an operator, so a comparison in a default does not swallow the comma before a
    generic parameter: the documented bare names find both source parameters."""
    _check_parameters("(a, b) => X", "(a: boolean = x < y, b: Map<string, number>) => Y", ".ts", None)
    _check_parameters("(a, c) => X", "(a: boolean = x < y, b: Map<string, number>) => Y", ".ts",
                      "`c` is not a source parameter")


FETCH_FULL = {"name": "fetch", "kind": "function",
              "params": "url: str, method: str = 'GET', timeout: float | None = None, retries: int = 0",
              "return_type": "Response", "description": "Fetches."}
FETCH_SHARED = {"name": "fetch", "kind": "function", "params": "each takes timeout=None, retries=0; url, method='GET'",
                "return_type": "Response", "signature_form": "partial", "description": "Fetches."}
FETCH_SURFACE = [{"name": "fetch", "kind": "function", "file": "pkg/http.py", "line": 3,
                  "signatureLine": "def fetch(url, method='GET', timeout=None, retries=0, verify=True) -> Response:",
                  "origin": "extraction"}]


def test_a_partial_form_in_the_shared_text_shape_keeps_its_label():
    """A name with two forms, its second a partial form in the shared-text shape (inventory-contract.md: the
    shared text, `; `, then its own members): an `omitted-optional` mismatch reported for that form, quoting its
    text with its return, is graded by that form's label, an Info `Partial signature`, with no warning that the
    mismatch quotes another form. A `;` in a form is read as written."""
    mismatch = {"name": "fetch", "line": 3, "form": 1, "difference": "omitted-optional",
                "documented_sig": "each takes timeout=None, retries=0; url, method='GET' -> Response",
                "source_sig": "def fetch(url, method='GET', timeout=None, retries=0, verify=True) -> Response",
                "issue": "leaves out the optional 'verify'"}
    out = mod.score([FETCH_FULL, FETCH_SHARED], ["fetch"], FETCH_SURFACE,
                    [{"file": "pkg/http.py", "signature_mismatches": [mismatch]}])
    assert [m["severity"] for m in out["mismatches"]] == ["Info"], out["warnings"]
    assert [g["title"] for g in out["gapRecords"]] == ["Partial signature: fetch (form 2 of 2)"]
    assert not any("whose text its `documented_sig` is not" in w for w in out["warnings"]), out["warnings"]


def test_an_entry_in_the_shared_text_shape_is_valid_and_planned_whole(tmp_path):
    """validate-inventory.py accepts an entry whose `params` is the shared-text shape the contract gives, and
    `plan` hands the judge the whole text as the check's documented form, shared text included."""
    shared = "each with the base fields id, scope=Scope(); content, title=None"
    response = _write(tmp_path / "inventory-response.txt", {"exports": [
        {"name": "Note", "kind": "class", "params": shared, "description": "A note.", "at": "SKILL.md:1"}],
        "references": [], "cross_check_mismatches": []})
    inventory = tmp_path / "inventory.json"
    proc = subprocess.run([sys.executable, str(SCRIPTS / "validate-inventory.py"), "--input", response,
                           "--output", str(inventory)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0 and json.loads(proc.stdout)["valid"] is True, proc.stdout + proc.stderr
    surface = _write(tmp_path / "surface.json", {"exports": [
        {"name": "Note", "kind": "class", "file": "pkg/notes.py", "line": 5, "signatureLine": "class Note(Record):",
         "origin": "extraction"}], "sets": {"all": ["Note"]}})
    proc = _run("plan", "--inventory", str(inventory), "--surface", surface)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    [group] = json.loads(proc.stdout)["files"]
    assert [check["documented"] for check in group["checks"]] == [{"params": shared}]


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


# #918: cognee's two run_pipeline functions. The surface records the orchestrator once, as a `pipelines` namespace
# member; the lightweight runner, which a lazy `__getattr__` passes on and no entry point exports, is an other
# declaration. The skill documents both, and a form whose own citations, at the place the inventory's `at` gives,
# name one of them is bound to it.
ORCHESTRATOR = "cognee/modules/pipelines/operations/pipeline.py"
LIGHTWEIGHT = "cognee/modules/pipelines/operations/run_pipeline.py"
ORCHESTRATOR_RECORD = {"name": "run_pipeline", "kind": "function", "file": ORCHESTRATOR, "line": 53,
                       "signatureLine": "async def run_pipeline(", "origin": "extraction"}
LIGHTWEIGHT_DECLARATION = {"name": "run_pipeline", "kind": "function", "file": LIGHTWEIGHT, "line": 37,
                           "signatureLine": "async def run_pipeline("}
HOMONYMS = {"exports": [ORCHESTRATOR_RECORD], "otherDeclarations": [LIGHTWEIGHT_DECLARATION],
            "sets": {"all": ["run_pipeline"]}}
ORCHESTRATOR_FORM = "`run_pipeline(tasks=None, data=None, datasets=None)` runs a pipeline"
ORCHESTRATOR_LINE = f"{ORCHESTRATOR_FORM} [AST:{ORCHESTRATOR}:L53]."
LIGHTWEIGHT_LINE = (f"`from cognee.pipelines import run_pipeline` gives the lightweight runner "
                    f"`run_pipeline(steps, *, data=None, context=None) -> list` [AST:{LIGHTWEIGHT}:L37].")
# A line between two forms: a form's own citations are those of its line and the next non-blank one.
APART = "The two functions differ."
# SKILL.md's lines 3 and 7 write the two forms.
HOMONYM_SKILL = f"# Demo\n\n{ORCHESTRATOR_LINE}\n\n{APART}\n\n{LIGHTWEIGHT_LINE}\n"


def _run_pipeline(orchestrator_at: str | None = "SKILL.md:3", lightweight_at: str | None = "SKILL.md:7") -> list:
    """The two forms the skill documents, each entry at its place (no `at` for None)."""
    entries = [{"name": "run_pipeline", "kind": "function", "params": "tasks=None, data=None, datasets=None",
                "description": "The dataset-aware orchestrator.", "at": orchestrator_at},
               {"name": "run_pipeline", "kind": "function", "params": "steps, *, data=None, context=None",
                "return_type": "list", "description": "The lightweight runner.", "at": lightweight_at}]
    return [{k: v for k, v in e.items() if v is not None} for e in entries]


RUN_PIPELINE = _run_pipeline()
ORCHESTRATOR_BOUND = {"form": 0, "file": ORCHESTRATOR, "line": 53, "signatureLine": "async def run_pipeline("}
LIGHTWEIGHT_BOUND = {"form": 1, "file": LIGHTWEIGHT, "line": 37, "signatureLine": "async def run_pipeline("}


def _homonym_plan(tmp_path: Path, tree: dict[str, str] | None, surface: dict = HOMONYMS,
                  inventory: list | None = None, output: Path | None = None) -> subprocess.CompletedProcess:
    """plan over `inventory` (RUN_PIPELINE) and `surface`, with the skill `tree` as --skill-dir (none when None)."""
    args = []
    if tree is not None:
        for rel, text in tree.items():
            _write(tmp_path / "skill" / rel, text)
        args = ["--skill-dir", str(tmp_path / "skill")]
    if output is not None:
        args += ["--output", str(output)]
    entries = RUN_PIPELINE if inventory is None else inventory
    path = _write(tmp_path / "inventory.json", {"exports": entries, "cross_check_mismatches": []})
    proc = _run("plan", "--inventory", path, "--surface", _write(tmp_path / "surface.json", surface), *args)
    assert proc.returncode == 0, proc.stderr
    return proc


def _homonym_check(plan: dict) -> dict:
    """The run_pipeline check, which stays at the orchestrator's record with no candidates."""
    assert plan["compared"] == 1
    [group] = plan["files"]
    [check] = group["checks"]
    assert (group["file"], check["line"]) == (ORCHESTRATOR, 53), "the planned record is the surface's record"
    assert "candidates" not in check, "an other declaration is never a candidate"
    assert check["documented"] == {"params": "tasks=None, data=None, datasets=None"}
    assert check["alternatives"] == [{"params": "steps, *, data=None, context=None", "return_type": "list"}]
    return check


LIGHTWEIGHT_BLOCK = "```python\nasync def run_pipeline(\n    steps,\n) -> list\n```\n"


@pytest.mark.parametrize("tree, lightweight_at, bound", [
    ({"SKILL.md": HOMONYM_SKILL}, "SKILL.md:7", [ORCHESTRATOR_BOUND, LIGHTWEIGHT_BOUND]),
    ({"SKILL.md": f"# Demo\n\n{ORCHESTRATOR_FORM}.\n\n{APART}\n\n{LIGHTWEIGHT_LINE}\n"}, "SKILL.md:7",
     [LIGHTWEIGHT_BOUND]),
    ({"SKILL.md": f"# Demo\n\n{ORCHESTRATOR_LINE}\n",
      "references/pipelines.md": f"### Lightweight runner: run_pipeline\n\n[SRC:./{LIGHTWEIGHT}:L37-L45]\n"},
     "references/pipelines.md:1", [ORCHESTRATOR_BOUND, LIGHTWEIGHT_BOUND]),
    ({"SKILL.md": f"# Demo\n\n{ORCHESTRATOR_LINE}\n\n{APART}\n\n`run_pipeline(steps)` and its loop "
                  f"[SRC:{LIGHTWEIGHT}:L30-50].\n"}, "SKILL.md:7", [ORCHESTRATOR_BOUND, LIGHTWEIGHT_BOUND]),
    ({"SKILL.md": f"# Demo\n\n{ORCHESTRATOR_LINE}\n\n{LIGHTWEIGHT_BLOCK}\n`[AST:{LIGHTWEIGHT}:L37]`\n"},
     "SKILL.md:6", [ORCHESTRATOR_BOUND, LIGHTWEIGHT_BOUND]),
    ({"SKILL.md": f"# Demo\n\n{ORCHESTRATOR_LINE}\n\n```python\n# [AST:{LIGHTWEIGHT}]\n"
                  "async def run_pipeline(\n    steps,\n) -> list\n```\n"},
     "SKILL.md:7", [ORCHESTRATOR_BOUND, LIGHTWEIGHT_BOUND]),
], ids=["both-cited", "only-the-other-declaration-cited", "a-heading-then-its-citation", "a-range-that-holds-it",
        "the-line-after-its-fenced-block", "a-comment-heading-its-fenced-block"])
def test_a_form_whose_own_citation_names_a_declaration_is_bound_to_it(tmp_path, tree, lightweight_at, bound):
    """#918 (oms-cognee run_pipeline): each form whose own citations name one declaration of the name, the
    orchestrator's surface record or the lightweight runner's other declaration, is bound to it, so the judge
    compares it with that declaration alone. The check stays at the surface's record and offers no candidate: an
    other declaration reaches the judge only through a binding, and is never the planned record, even when the
    skill cites only it."""
    plan = json.loads(_homonym_plan(tmp_path, tree, inventory=_run_pipeline(lightweight_at=lightweight_at)).stdout)
    assert _homonym_check(plan)["bound"] == bound


@pytest.mark.parametrize("tree, inventory", [
    ({"SKILL.md": f"# Demo\n\n{ORCHESTRATOR_FORM}.\n\n`run_pipeline(steps, *, data=None, context=None)`.\n"}, None),
    ({"SKILL.md": f"# Demo\n\n{ORCHESTRATOR_FORM}.\n\n{APART}\n\n`run_pipeline(steps, *, data=None, context=None)`."
                  f"\n\n{APART}\n\nThe steps run in order [AST:{LIGHTWEIGHT}:L37].\n"}, None),
    ({"SKILL.md": f"# Demo\n\n{ORCHESTRATOR_FORM}.\n\n{APART}\n\n`run_pipeline(steps)` needs its imports "
                  f"[SRC:{LIGHTWEIGHT}:L12] [SRC:{LIGHTWEIGHT}:L20].\n"}, None),
    ({"SKILL.md": f"# Demo\n\n{ORCHESTRATOR_FORM}.\n\n{APART}\n\n`run_pipeline(steps)` imports its helpers first "
                  f"[SRC:{LIGHTWEIGHT}:L1-36].\n"}, None),
    ({"SKILL.md": f"# Demo\n\n{ORCHESTRATOR_FORM} [AST:{ORCHESTRATOR}:L53] [AST:{LIGHTWEIGHT}:L37].\n"},
     _run_pipeline("SKILL.md:3", "SKILL.md:3")),
    ({"SKILL.md": HOMONYM_SKILL}, _run_pipeline(None, None)),
    ({"SKILL.md": HOMONYM_SKILL}, _run_pipeline("references/gone.md:3", "SKILL.md:99")),
    (None, None),
], ids=["not-cited", "cited-at-another-place", "its-file-cited-above-its-declaration", "a-range-that-stops-before-it",
        "both-declarations-named", "no-at", "a-place-the-skill-lacks", "no-skill-dir"])
def test_a_form_bound_to_nothing_is_planned_as_before(tmp_path, tree, inventory):
    """#918: a form whose own citations name no declaration of the name, or two, is bound to nothing, and a plan
    with no binding is byte for byte the plan of a surface with no `otherDeclarations` and an inventory with no
    `at`: the check at the record, with no candidate. A citation of the runner's file at lines above its
    declaration (its imports), or a citation at a place that is not the form's, names nothing; one in its body
    names it (test_a_citation_in_a_declaration_s_body_names_it)."""
    plan = _homonym_plan(tmp_path / "with", tree, inventory=inventory)
    bare = [{k: v for k, v in e.items() if k != "at"} for e in (RUN_PIPELINE if inventory is None else inventory)]
    without = _homonym_plan(tmp_path / "without", tree, {k: v for k, v in HOMONYMS.items()
                                                         if k != "otherDeclarations"}, bare)
    assert plan.stdout == without.stdout
    assert "bound" not in _homonym_check(json.loads(plan.stdout))


def test_a_form_whose_place_validation_drops_is_planned_unbound(tmp_path):
    """#918: an `at` validate-inventory.py finds bad never refuses the inventory; it drops it with a warning. The
    lightweight form's `at` names the line after its form, which does not write `run_pipeline` but cites the
    lightweight runner: read as given, plan would bind the form there. Validated, the inventory keeps the entry
    without that `at`, and plan leaves the form unbound, byte for byte the plan of an inventory with no `at`."""
    tree = {"SKILL.md": f"# Demo\n\n{ORCHESTRATOR_FORM}.\n\n{APART}\n\n"
                        f"`run_pipeline(steps, *, data=None, context=None)`.\n\n{APART}\n\n"
                        f"The steps run in order [AST:{LIGHTWEIGHT}:L37].\n"}
    misplaced = _run_pipeline(lightweight_at="SKILL.md:11")
    raw = json.loads(_homonym_plan(tmp_path / "raw", tree, inventory=misplaced).stdout)
    assert _homonym_check(raw)["bound"] == [LIGHTWEIGHT_BOUND], "the bad place, read as given, binds"
    skill = tmp_path / "skill"
    for rel, text in tree.items():
        _write(skill / rel, text)
    response = _write(tmp_path / "inventory-response.txt", {"exports": misplaced, "cross_check_mismatches": []})
    inventory = tmp_path / "inventory.json"
    proc = subprocess.run([sys.executable, str(SCRIPTS / "validate-inventory.py"), "--input", response,
                           "--skill-package", str(skill), "--output", str(inventory)], capture_output=True,
                          text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["warnings"] == [
        "exports[1] (`run_pipeline`): `at` \"SKILL.md:11\" is a line that does not write `run_pipeline`; it is "
        "dropped and the form is compared as one whose citations name no declaration"]
    validated = json.loads(inventory.read_bytes())["exports"]
    assert [e.get("at") for e in validated] == ["SKILL.md:3", None]
    plan = _homonym_plan(tmp_path / "validated", tree, inventory=validated)
    assert "bound" not in _homonym_check(json.loads(plan.stdout))
    without = _homonym_plan(tmp_path / "without", tree, inventory=_run_pipeline(None, None))
    assert plan.stdout == without.stdout


def test_a_form_is_bound_to_one_of_two_surface_records(tmp_path):
    """#918 with #830's candidates: composeStories has records in react and vue3. Each form's own citation names
    one of them, so each is bound to its own, while the check, whose citations name both files, keeps every record
    as a candidate for a form bound to none. A form whose own citation names a record the file-level citations do
    not settle on is still bound to it: the check sits at vue3's record and the fenced form is bound to react's."""
    usage = {"name": "composeStories", "kind": "function", "usage_signature": "composeStories(stories)"}
    react_line = f"`composeStories(csfExports, projectAnnotations?)` [AST:{REACT}:L40]"
    vue_line = f"`composeStories(stories)` [AST:{VUE}:L12]"
    surface = {"exports": COMPOSE_RECORDS, "sets": {"all": ["composeStories"]}}
    tree = {"SKILL.md": f"# Demo\n\n{react_line}\n\n{APART}\n\n{vue_line}\n"}
    plan = json.loads(_homonym_plan(tmp_path / "two", tree, surface,
                                    [{**COMPOSE, "at": "SKILL.md:3"}, {**usage, "at": "SKILL.md:7"}]).stdout)
    [group] = plan["files"]
    [check] = group["checks"]
    assert group["file"] == REACT and [(c["file"], c["line"]) for c in check["candidates"]] == [(REACT, 40), (VUE, 12)]
    assert [(b["form"], b["file"], b["line"]) for b in check["bound"]] == [(0, REACT, 40), (1, VUE, 12)]
    block = (f"# Demo\n\n```ts\nexport function composeStories(csfExports, projectAnnotations?)\n```\n\n"
             f"`[AST:{REACT}:L40]`\n\n{vue_line}\n")
    plan = json.loads(_homonym_plan(tmp_path / "settled", {"SKILL.md": block}, surface,
                                    [{**COMPOSE, "at": "SKILL.md:4"}, {**usage, "at": "SKILL.md:9"}]).stdout)
    [group] = plan["files"]
    [check] = group["checks"]
    assert group["file"] == VUE and "candidates" not in check
    assert [(b["form"], b["file"], b["line"]) for b in check["bound"]] == [(0, REACT, 40), (1, VUE, 12)]
    # a citation of a file with no line names every declaration in it: two records in one file bind nothing
    twice = {"exports": [*COMPOSE_RECORDS, {**COMPOSE_RECORDS[1], "line": 90}], "sets": {"all": ["composeStories"]}}
    tree = {"SKILL.md": f"# Demo\n\n`composeStories(x)` [AST:{REACT}]\n"}
    plan = json.loads(_homonym_plan(tmp_path / "whole-file", tree, twice, [{**COMPOSE, "at": "SKILL.md:3"}]).stdout)
    assert "bound" not in plan["files"][0]["checks"][0]


# Two forms of the name written next to each other, each test's orchestrator form first: its own citations are never
# the other form's.
FENCED_TWO = ("```python\nasync def run_pipeline(tasks=None, data=None, datasets=None): ...\n"
              "async def run_pipeline(steps, *, data=None, context=None) -> list: ...\n```\n")


@pytest.mark.parametrize("text, at, bound", [
    (f"# Demo\n\n{ORCHESTRATOR_LINE}\n{LIGHTWEIGHT_LINE}\n", ("SKILL.md:3", "SKILL.md:4"),
     [ORCHESTRATOR_BOUND, LIGHTWEIGHT_BOUND]),
    ("# Demo\n\n| Export | Signature |\n| --- | --- |\n| `run_pipeline` | `(tasks=None, data=None, datasets=None)` |\n"
     f"| `run_pipeline` | `(steps, *, data=None, context=None) -> list` [AST:{LIGHTWEIGHT}:L37] |\n",
     ("SKILL.md:5", "SKILL.md:6"), [LIGHTWEIGHT_BOUND]),
    (f"# Demo\n\n{FENCED_TWO}\n`[AST:{LIGHTWEIGHT}:L37]`\n", ("SKILL.md:4", "SKILL.md:5"), []),
    (f"# Demo\n\nTwo functions share the name:\n\n```python\n# [AST:{ORCHESTRATOR}:L53]\n"
     "async def run_pipeline(tasks=None, data=None, datasets=None): ...\n\n"
     f"# [AST:{LIGHTWEIGHT}:L37]\nasync def run_pipeline(steps, *, data=None, context=None) -> list: ...\n```\n",
     ("SKILL.md:7", "SKILL.md:10"), [ORCHESTRATOR_BOUND, LIGHTWEIGHT_BOUND]),
    ("# Demo\n\n```python\nasync def run_pipeline(tasks=None, data=None, datasets=None): ...\n```\n\n"
     "`cognee.pipelines` declares its own `run_pipeline`, the lightweight runner "
     f"`run_pipeline(steps, *, data=None, context=None) -> list` [AST:{LIGHTWEIGHT}:L37].\n",
     ("SKILL.md:4", "SKILL.md:7"), [LIGHTWEIGHT_BOUND]),
], ids=["adjacent-lines-each-cited", "an-uncited-row-then-a-cited-row", "one-block-of-both-then-a-citation",
        "one-block-of-both-each-under-its-comment", "a-fenced-form-then-a-note-on-the-other"])
def test_a_neighbouring_place_s_citation_never_binds_a_form(tmp_path, text, at, bound):
    """#918 review: a form whose own line cites nothing is never bound by the citation of a neighbouring line that is
    another place of the name. The next table row, a note after the block that names the name and cites the other
    declaration, and the line after a block that holds both forms are not its own, so the orchestrator's correct
    form stays compared with its surface record, as before, never strictly with the lightweight runner; and in one
    block that declares both, each declaration's own comment just above it binds it."""
    inventory = _run_pipeline(*at)
    plan = json.loads(_homonym_plan(tmp_path, {"SKILL.md": text}, inventory=inventory).stdout)
    assert _homonym_check(plan).get("bound", []) == bound


@pytest.mark.parametrize("second", [
    {"name": "run_pipeline", "kind": "function", "params": "", "description": "Takes none."},
    {"name": "run_pipeline", "kind": "function", "description": "Named, with no form."},
], ids=["a-form-the-plan-drops", "an-entry-with-no-form"])
def test_every_place_the_inventory_gives_the_name_shares_a_block(tmp_path, second):
    """A block's own citations belong to its one place of the name, counted over every entry of the name with an
    `at`: one whose form the plan drops (it lists no member, after one that does) and one with no form too."""
    _write(tmp_path / "skill" / "SKILL.md", f"# Demo\n\n{FENCED_TWO}\n`[AST:{LIGHTWEIGHT}:L37]`\n")
    inventory = [_run_pipeline("SKILL.md:4")[0], {**second, "at": "SKILL.md:5"}]
    plan = mod.plan(inventory, ["run_pipeline"], [ORCHESTRATOR_RECORD], str(tmp_path / "skill"),
                    [LIGHTWEIGHT_DECLARATION])
    [check] = plan["files"][0]["checks"]
    assert "alternatives" not in check and "bound" not in check
    plan = mod.plan(inventory[:1], ["run_pipeline"], [ORCHESTRATOR_RECORD], str(tmp_path / "skill"),
                    [LIGHTWEIGHT_DECLARATION])
    assert plan["files"][0]["checks"][0]["bound"] == [{**LIGHTWEIGHT_BOUND, "form": 0}], "alone in its block"


def test_one_declaration_recorded_twice_binds_a_form(tmp_path):
    """A declaration the surface records twice, at one file and line (as a namespace member and as an export), is one
    declaration: a form whose citation names it is bound to it, not left unbound as naming two."""
    twice = {**HOMONYMS, "exports": [ORCHESTRATOR_RECORD, {**ORCHESTRATOR_RECORD, "origin": "namespace"}]}
    plan = json.loads(_homonym_plan(tmp_path, {"SKILL.md": HOMONYM_SKILL}, twice).stdout)
    assert _homonym_check(plan)["bound"] == [ORCHESTRATOR_BOUND, LIGHTWEIGHT_BOUND]


def test_two_entries_of_one_form_bind_it_by_all_their_places(tmp_path):
    """Two entries that say the same thing are one form: its own citations are those of both places, so one place
    that names the runner binds it, and a second place that names the orchestrator leaves it bound to neither. A
    second place that is the orchestrator form's own line writes two forms that differ, so its citation binds
    neither of them: the orchestrator's form, written only there, is left unbound, and the runner's is bound by
    its other place."""
    tree = {"SKILL.md": f"{HOMONYM_SKILL}\n`run_pipeline(steps)`.\n"}
    lightweight = _run_pipeline()[1]
    plan = json.loads(_homonym_plan(tmp_path / "one", tree, inventory=[
        _run_pipeline()[0], lightweight, {**lightweight, "at": "SKILL.md:9"}]).stdout)
    assert _homonym_check(plan)["bound"] == [ORCHESTRATOR_BOUND, LIGHTWEIGHT_BOUND]
    cited = {"SKILL.md": f"{HOMONYM_SKILL}\n`run_pipeline(steps)` [AST:{ORCHESTRATOR}:L53].\n"}
    plan = json.loads(_homonym_plan(tmp_path / "two", cited, inventory=[
        _run_pipeline()[0], lightweight, {**lightweight, "at": "SKILL.md:9"}]).stdout)
    assert _homonym_check(plan)["bound"] == [ORCHESTRATOR_BOUND]
    plan = json.loads(_homonym_plan(tmp_path / "shared", tree, inventory=[
        _run_pipeline()[0], lightweight, {**lightweight, "at": "SKILL.md:3"}]).stdout)
    assert _homonym_check(plan)["bound"] == [LIGHTWEIGHT_BOUND]


def _plan_in(tmp_path: Path, tree: dict[str, str], inventory: list[dict], exports: list[dict],
             others: list[dict] | None = None, names: list[str] | None = None) -> dict:
    """mod.plan over `inventory`, the surface `exports` and `others`, with the skill `tree` as its skill_dir."""
    for rel, text in tree.items():
        _write(tmp_path / "skill" / rel, text)
    names = names if names is not None else sorted({e["name"] for e in inventory})
    return mod.plan(inventory, names, exports, str(tmp_path / "skill"), others)


def _bound(plan: dict, name: str) -> list[tuple]:
    """(form, file, line) of each form plan bound for `name`'s check."""
    [check] = [c for group in plan["files"] for c in group["checks"] if c["name"] == name]
    return [(b["form"], b["file"], b["line"]) for b in check.get("bound", [])]


def _without_the_edge_rules(monkeypatch) -> None:
    """plan as it read a form's citations before the shared-place and body-span rules: every place's citations,
    and a declaration named at its line alone."""
    monkeypatch.setattr(mod, "_shared_places", lambda inventory: {})
    monkeypatch.setattr(mod, "_span_end", lambda located, file, line: None)


# #918, a place shared by two forms (oms-storybook-react-vite references/core-api.md:102): a table row documents
# core's composeStories and quotes React's form as a contrast, citing only core's declaration.
CORE = "code/core/src/preview-api/modules/store/csf/portable-stories.ts"
CORE_COMPOSE_RECORDS = [
    {"name": "composeStories", "kind": "function", "file": CORE, "line": 274,
     "signatureLine": "export function composeStories<TModule extends Store_CSFExports>(", "origin": "extraction"},
    {"name": "composeStories", "kind": "function", "file": REACT, "line": 148,
     "signatureLine": "export function composeStories<TModule extends Store_CSFExports<ReactRenderer, any>>(",
     "origin": "extraction"},
]
CORE_FORM = {"name": "composeStories", "kind": "function",
             "params": "storiesImport: TModule, globalConfig: ProjectAnnotations<Renderer>, "
                       "composeStoryFn: ComposeStoryFn = defaultComposeStory"}
REACT_FORM = {"name": "composeStories", "kind": "function", "params": "csfExports, projectAnnotations?"}
CONTRAST_ROW = ("| `composeStories` | function | Core's renderer-agnostic form: `composeStories("
                "storiesImport: TModule, globalConfig: ProjectAnnotations<Renderer>, "
                "composeStoryFn: ComposeStoryFn = defaultComposeStory)`. "
                "Story authors on React+Vite import `composeStories(csfExports, projectAnnotations?)` from "
                f"`@storybook/react-vite` instead. | `[AST:{CORE}:L274]` |")
# references/core-api.md's line 3 is the contrast row; its line 5, no place of a form, cites React's declaration, so
# the skill cites both files on a line that names composeStories and the check offers both as candidates (#830).
CORE_API = (f"| Export | Kind | Description | Source |\n| --- | --- | --- | --- |\n{CONTRAST_ROW}\n\n"
            f"Story authors import `composeStories` from `@storybook/react-vite` `[AST:{REACT}:L148]`.\n")
# SKILL.md's line 3 is a row of React's form alone.
REACT_ROW = ("| Export | Import | Description | Source |\n| --- | --- | --- | --- |\n"
             "| `composeStories` | `@storybook/react-vite` | `composeStories(csfExports, projectAnnotations?)`: render "
             f"stories in Vitest | `[AST:{REACT}:L148]` |\n")


def test_a_place_that_writes_two_forms_binds_neither(tmp_path, monkeypatch):
    """#918 (oms-storybook-react-vite composeStories): the contrast row writes core's form and React's, and cites
    core's declaration alone. Read for both forms, its citation bound React's form to core's declaration, where
    the judge found core's required `globalConfig` missing: a Critical false positive. A place that writes two
    forms of the name that differ gives none of them a citation, so each is compared as one with no own citation:
    byte for byte the plan of an inventory with no `at`, the check at the first record with both records as
    candidates, React's form matching the one it was written for."""
    tree = {"references/core-api.md": CORE_API}
    at = "references/core-api.md:3"
    inventory = [{**CORE_FORM, "at": at}, {**REACT_FORM, "at": at}]
    plan = _plan_in(tmp_path, tree, inventory, CORE_COMPOSE_RECORDS)
    assert _bound(plan, "composeStories") == []
    [check] = plan["files"][0]["checks"]
    assert [(c["file"], c["line"]) for c in check["candidates"]] == [(CORE, 274), (REACT, 148)]
    bare = [{k: v for k, v in e.items() if k != "at"} for e in inventory]
    assert plan == _plan_in(tmp_path / "bare", tree, bare, CORE_COMPOSE_RECORDS)
    _without_the_edge_rules(monkeypatch)
    assert _bound(_plan_in(tmp_path / "before", tree, inventory, CORE_COMPOSE_RECORDS), "composeStories") == [
        (0, CORE, 274), (1, CORE, 274)], "the false positive: React's form bound to core's declaration"


def test_a_form_at_a_shared_place_is_bound_by_its_other_places(tmp_path):
    """#918: React's form is also written in SKILL.md's row, which cites React's declaration alone. Its own
    citations are those of its other places, as for any form written at several places, so it is bound to
    React's declaration; core's form, written only at the shared row, stays unbound and keeps the candidates."""
    tree = {"references/core-api.md": CORE_API, "SKILL.md": REACT_ROW}
    inventory = [{**CORE_FORM, "at": "references/core-api.md:3"}, {**REACT_FORM, "at": "references/core-api.md:3"},
                 {**REACT_FORM, "at": "SKILL.md:3"}]
    plan = _plan_in(tmp_path, tree, inventory, CORE_COMPOSE_RECORDS)
    assert _bound(plan, "composeStories") == [(1, REACT, 148)]
    assert "candidates" in plan["files"][0]["checks"][0]


@pytest.mark.parametrize("entries, bound", [
    ([REACT_FORM, REACT_FORM], [(0, CORE, 274)]),
    ([REACT_FORM, {**REACT_FORM, "signature_form": "partial"}], [(0, CORE, 274)]),
    ([REACT_FORM, {"name": "composeStories", "kind": "function", "description": "Named, with no form."}],
     [(0, CORE, 274)]),
    ([REACT_FORM, {"name": "composeStory", "kind": "function", "params": "story, componentAnnotations"}],
     [(0, CORE, 274)]),
    ([REACT_FORM, {"name": "composeStories", "kind": "method", "owner": "portable", "params": "stories"}],
     [(0, CORE, 274)]),
    ([{**REACT_FORM, "params": "csfExports"}, {**REACT_FORM, "params": "csfExports, projectAnnotations"},
      {**REACT_FORM, "params": "csfExports, projectAnnotations, composeStoryFn"}], []),
], ids=["one-form-written-twice", "one-form-and-its-partial-label", "an-entry-with-no-form",
        "another-name-s-form", "a-method-of-the-name", "overloads-of-one-declaration"])
def test_only_two_forms_of_the_name_that_differ_share_a_place(tmp_path, entries, bound):
    """#918: entries that say the same thing at one place (the partial label aside) are one form, and their place
    still binds it; an entry with no form writes no form there, another name's form is no form of this name, and
    neither is a `method` of the name (a method, never compared as the name's form). A row of several overloads of
    one of the name's two declarations writes forms that differ, so it binds none of them: each is compared as one
    with no own citation, as before #918 bound any."""
    inventory = [{**entry, "at": "references/core-api.md:3"} for entry in entries]
    exports = [*CORE_COMPOSE_RECORDS, {"name": "composeStory", "kind": "function", "file": CORE, "line": 90,
                                       "signatureLine": "export function composeStory(", "origin": "extraction"}]
    plan = _plan_in(tmp_path, {"references/core-api.md": CORE_API}, inventory, exports, names=["composeStories"])
    assert _bound(plan, "composeStories") == bound


CORE_PER_FILE = {"name": "composeStories", "kind": None, "file": CORE, "line": None, "signatureLine": None,
                 "origin": "per-file"}


@pytest.mark.parametrize("exports, others, bound", [
    (CORE_COMPOSE_RECORDS[:1], None, [(0, CORE, 274), (1, CORE, 274)]),
    ([CORE_PER_FILE, *CORE_COMPOSE_RECORDS[:1]], None, [(0, CORE, 274), (1, CORE, 274)]),
    ([*CORE_COMPOSE_RECORDS[:1], {**CORE_COMPOSE_RECORDS[0], "line": 300}], None, []),
    (CORE_COMPOSE_RECORDS[:1], CORE_COMPOSE_RECORDS[1:], []),
    ([*CORE_COMPOSE_RECORDS[:1], {**CORE_PER_FILE, "file": REACT}], None, []),
], ids=["one-declaration", "a-per-file-record-beside-it", "two-lines-of-one-file", "an-other-declaration-elsewhere",
        "a-per-file-record-in-another-file"])
def test_a_shared_place_of_a_name_declared_once_still_binds(tmp_path, exports, others, bound):
    """#918 (oms-storybook-react-vite actions, mocked and spyOn): a row of a name's overloads writes forms that
    differ, but a name declared once, in one file and at one line there (a per-file record with no line beside it
    is no other declaration), has no other declaration its citation could bind a form to. Its shared place keeps
    its citations, so each form is bound to that declaration, at its line, where the check of mocked and spyOn
    gives none. A name declared at two lines of one file, or in two files (an `otherDeclarations` entry or a
    per-file record with no line included), gives a shared place's forms no citation."""
    at = "references/core-api.md:3"
    inventory = [{**CORE_FORM, "at": at}, {**REACT_FORM, "at": at}]
    plan = _plan_in(tmp_path, {"references/core-api.md": CORE_API}, inventory, exports, others)
    assert _bound(plan, "composeStories") == bound
    if exports[0] is CORE_PER_FILE:
        assert plan["files"][0]["checks"][0]["line"] is None, "the line-less record's check gives the judge none"


# #918, a citation in a declaration's body (oms-cognee references/pipelines-and-datapoints.md): the extraction
# records no declaration's last line, so a declaration's span runs from its line to the line before the next
# declaration the surface records in its file, of any name, or to the end of the file.
TYPED_ORCHESTRATOR = ("```python\nasync def run_pipeline(\n    tasks: list[Task] | None = None,\n    data=None,\n"
                      "    datasets: list[str] | None = None,\n)\n```\n")
LIGHTWEIGHT_USAGE = ("```python\nfrom cognee.pipelines import task, run_pipeline\n\nresults = await run_pipeline(\n"
                     "    [classify(), extract(graph_model=KnowledgeGraph)],\n    data=raw_input,\n)\n```\n")
# SKILL.md: the typed orchestrator block's `def` line is 4, the line after it cites the orchestrator's body (11);
# the usage block's call is line 16, the line after it cites the runner's body (21).
BODY_SKILL = (f"# Demo\n\n{TYPED_ORCHESTRATOR}\n`tasks` is a task list or a resolver. "
              f"[SRC:{ORCHESTRATOR}:L70-L79]\n\n{LIGHTWEIGHT_USAGE}\n- Each step receives the previous step's "
              f"output. [SRC:{LIGHTWEIGHT}:L46-L61]\n")
TYPED_ORCHESTRATOR_FORM = {"name": "run_pipeline", "kind": "function",
                           "params": "tasks: list[Task] | None = None, data=None, datasets: list[str] | None = None",
                           "at": "SKILL.md:4"}
LIGHTWEIGHT_USAGE_FORM = {"name": "run_pipeline", "kind": "function",
                          "usage_signature": "run_pipeline([classify(), extract(graph_model=KnowledgeGraph)], "
                                             "data=raw_input)", "at": "SKILL.md:16"}


def test_a_citation_in_a_declaration_s_body_names_it(tmp_path, monkeypatch):
    """#918 (oms-cognee run_pipeline): the typed orchestrator block is followed by a citation of pipeline.py's
    L70-L79, inside the orchestrator declared at its L53, and the lightweight usage block by one of
    run_pipeline.py's L46-L61, inside the runner declared at its L37. Neither range holds a `def` line, so read at
    its line alone neither named a declaration and both forms were compared with the surface's record. A citation
    of a declaration's body names it: each form is bound to its own function."""
    inventory = [TYPED_ORCHESTRATOR_FORM, LIGHTWEIGHT_USAGE_FORM]
    plan = _plan_in(tmp_path, {"SKILL.md": BODY_SKILL}, inventory, [ORCHESTRATOR_RECORD], [LIGHTWEIGHT_DECLARATION])
    assert _bound(plan, "run_pipeline") == [(0, ORCHESTRATOR, 53), (1, LIGHTWEIGHT, 37)]
    _without_the_edge_rules(monkeypatch)
    plan = _plan_in(tmp_path / "before", {"SKILL.md": BODY_SKILL}, inventory, [ORCHESTRATOR_RECORD],
                    [LIGHTWEIGHT_DECLARATION])
    assert _bound(plan, "run_pipeline") == []


RUN_STEPS = {"name": "run_steps", "kind": "function", "file": LIGHTWEIGHT, "line": 80,
             "signatureLine": "async def run_steps(", "origin": "extraction"}


@pytest.mark.parametrize("cited, exports, others, bound", [
    ("L82", [ORCHESTRATOR_RECORD, RUN_STEPS], [LIGHTWEIGHT_DECLARATION], []),
    ("L82", [ORCHESTRATOR_RECORD], [LIGHTWEIGHT_DECLARATION, {**RUN_STEPS, "name": "run_steps_now"}], []),
    ("L60-L85", [ORCHESTRATOR_RECORD, RUN_STEPS], [LIGHTWEIGHT_DECLARATION], [(0, LIGHTWEIGHT, 37)]),
    ("L79", [ORCHESTRATOR_RECORD, RUN_STEPS], [LIGHTWEIGHT_DECLARATION], [(0, LIGHTWEIGHT, 37)]),
    ("L82", [ORCHESTRATOR_RECORD], [LIGHTWEIGHT_DECLARATION], [(0, LIGHTWEIGHT, 37)]),
    ("L36", [ORCHESTRATOR_RECORD], [LIGHTWEIGHT_DECLARATION], []),
], ids=["past-the-next-declaration", "past-another-name-s-other-declaration", "a-range-that-reaches-into-it",
        "its-last-line", "no-declaration-follows-it", "the-line-above-it"])
def test_a_declaration_s_span_ends_before_the_next_one_in_its_file(tmp_path, cited, exports, others, bound):
    """#918: a declaration's span ends on the line before the next declaration the surface records in its file,
    of any name, an exported one or an other declaration, and runs to the end of the file when none follows.
    A citation past it names nothing, one that reaches into it names it."""
    tree = {"SKILL.md": f"# Demo\n\n`run_pipeline(steps)` hands each step on [SRC:{LIGHTWEIGHT}:{cited}].\n"}
    inventory = [{"name": "run_pipeline", "kind": "function", "params": "steps", "at": "SKILL.md:3"}]
    plan = _plan_in(tmp_path, tree, inventory, exports, others, names=["run_pipeline"])
    assert _bound(plan, "run_pipeline") == bound


@pytest.mark.parametrize("cited, bound", [
    (f"[AST:{REACT}:L60-L70]", [(0, REACT, 40)]),
    (f"[AST:{REACT}:L95]", [(0, REACT, 90)]),
    (f"[AST:{REACT}:L90]", [(0, REACT, 90)]),
    (f"[AST:{REACT}:L89]", [(0, REACT, 40)]),
    (f"[AST:{REACT}:L80-L95]", []),
    (f"[AST:{REACT}:L60] [AST:{REACT}:L95]", []),
], ids=["the-first-one-s-body", "the-second-one-s-body", "the-second-one-s-line", "the-first-one-s-last-line",
        "a-range-over-both", "a-line-of-each"])
def test_a_citation_of_two_declarations_bodies_names_both(tmp_path, cited, bound):
    """#918: two declarations of the name in one file each span up to the next: the first ends on the line before
    the second's, which names the second alone. A citation names each one it holds a line of, and a form whose
    citations name both is bound to neither."""
    twice = [*COMPOSE_RECORDS, {**COMPOSE_RECORDS[1], "line": 90}]
    tree = {"SKILL.md": f"# Demo\n\n`composeStories(x)` {cited}\n"}
    plan = _plan_in(tmp_path, tree, [{**COMPOSE, "at": "SKILL.md:3"}], twice)
    assert _bound(plan, "composeStories") == bound


def test_the_edge_rules_change_nothing_else(tmp_path, monkeypatch):
    """#918: on a skill where no place writes two forms of a name and no citation reads a declaration's body
    without its line (citations at a `def` line, a range that holds it, a file with no line, the lines above a
    declaration, one form written twice at one place), plan is what it was before the shared-place and body-span
    rules, the check, its candidates and its `bound` alike."""
    skill = (f"# Demo\n\n{ORCHESTRATOR_LINE}\n\n{APART}\n\n{LIGHTWEIGHT_LINE}\n\n"
             f"`run_pipeline(steps)` and its loop [SRC:{LIGHTWEIGHT}:L30-50].\n\n"
             f"`run_pipeline(steps, data)` imports its helpers first [SRC:{LIGHTWEIGHT}:L1-36].\n\n"
             f"`composeStories(csfExports, projectAnnotations?)` [AST:{REACT}:L40]\n\n{APART}\n\n"
             f"`composeStories(stories)` [AST:{VUE}]\n")
    inventory = [*_run_pipeline("SKILL.md:3", "SKILL.md:7"),
                 {"name": "run_pipeline", "kind": "function", "usage_signature": "run_pipeline(steps)",
                  "at": "SKILL.md:9"},
                 {"name": "run_pipeline", "kind": "function", "params": "steps, data", "at": "SKILL.md:11"},
                 {**COMPOSE, "at": "SKILL.md:13"}, {**COMPOSE, "at": "SKILL.md:13"},
                 {"name": "composeStories", "kind": "function", "usage_signature": "composeStories(stories)",
                  "at": "SKILL.md:17"}]
    exports = [ORCHESTRATOR_RECORD, *COMPOSE_RECORDS]
    plan = _plan_in(tmp_path, {"SKILL.md": skill}, inventory, exports, [LIGHTWEIGHT_DECLARATION])
    assert _bound(plan, "run_pipeline") == [(0, ORCHESTRATOR, 53), (1, LIGHTWEIGHT, 37), (3, LIGHTWEIGHT, 37)]
    assert _bound(plan, "composeStories") == [(0, REACT, 40), (1, VUE, 12)]
    _without_the_edge_rules(monkeypatch)
    assert plan == _plan_in(tmp_path / "before", {"SKILL.md": skill}, inventory, exports, [LIGHTWEIGHT_DECLARATION])


LIGHTWEIGHT_MISMATCH = {"name": "run_pipeline", "line": 37, "file": LIGHTWEIGHT, "form": 1,
                        "source_sig": "(steps: list[BoundTask], *, data: Any = None, context: dict | None = None) "
                                      "-> list",
                        "documented_sig": "(steps, *, data=None, context=None) -> list[Any]",
                        "issue": "the return type is `list`, not `list[Any]`"}


def _homonym_score(tmp_path: Path, mismatches: list[dict], tree: dict | None = None, plan: bool = True) -> dict:
    """score of `mismatches`, reported from the orchestrator's group, with the plan of `tree` (HOMONYM_SKILL)."""
    output = tmp_path / "signature-plan.json"
    _homonym_plan(tmp_path, {"SKILL.md": HOMONYM_SKILL} if tree is None else tree, output=output)
    results = _write(tmp_path / "s.txt", json.dumps({"file": ORCHESTRATOR, "signature_mismatches": mismatches}))
    gaps = tmp_path / "signature-gaps.json"
    args = ["--plan", str(output)] if plan else []
    proc = _run("score", "--inventory", str(tmp_path / "inventory.json"), "--surface", str(tmp_path / "surface.json"),
                *args, "--results", results, "--gaps-output", str(gaps))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return {**json.loads(proc.stdout), "gaps": json.loads(gaps.read_text(encoding="utf-8"))}


def test_a_bound_form_s_mismatch_is_taken_at_its_declaration(tmp_path):
    """#918: the judge compared the lightweight form with the runner alone and reports its mismatch there, from
    the orchestrator's group: it is recorded at the runner's file and line, with no warning, its gap titled by its
    form as before. The bound declaration is no name, set or count. Without the plan its file is no file the check
    offered, as before: a warning, at the result's file."""
    out = _homonym_score(tmp_path, [LIGHTWEIGHT_MISMATCH])
    assert [(m["file"], m["line"], m["severity"]) for m in out["mismatches"]] == [(LIGHTWEIGHT, 37, "Critical")]
    assert not any("run_pipeline" in w for w in out["warnings"]), out["warnings"]
    [gap] = out["gaps"]
    assert (gap["source"], gap["title"]) == (f"{LIGHTWEIGHT}:37", "Signature mismatch: run_pipeline (form 2 of 2)")
    assert (out["comparedNames"], out["totalDocumented"], out["totalTypes"]) == (["run_pipeline"], 1, 0)
    out = _homonym_score(tmp_path / "no-plan", [LIGHTWEIGHT_MISMATCH], plan=False)
    assert [(m["file"], m["line"]) for m in out["mismatches"]] == [(ORCHESTRATOR, 37)]
    assert any(f"`{LIGHTWEIGHT}`, no file the plan offered its check at" in w for w in out["warnings"])


@pytest.mark.parametrize("named", [ORCHESTRATOR, None, "./" + ORCHESTRATOR], ids=["another-file", "none", "dotted"])
def test_a_bound_form_s_mismatch_named_elsewhere_is_taken_at_its_declaration(tmp_path, named):
    """#918: a judge that reports the bound lightweight form at the orchestrator (or names no file, from the
    orchestrator's group) is listed in `warnings`, and the mismatch is taken at the declaration the form is bound
    to, at its line, never at the orchestrator."""
    mismatch = {**LIGHTWEIGHT_MISMATCH, "file": named, "line": 53}
    out = _homonym_score(tmp_path, [mismatch])
    assert [(m["file"], m["line"]) for m in out["mismatches"]] == [(LIGHTWEIGHT, 37)]
    assert [g["source"] for g in out["gaps"]] == [f"{LIGHTWEIGHT}:37"]
    assert [w for w in out["warnings"] if "run_pipeline" in w] == [
        f"{ORCHESTRATOR}:53: a signature mismatch for `run_pipeline` names `{ORCHESTRATOR}`, but its form 1 is "
        f"bound to the declaration at {LIGHTWEIGHT}:37: recorded there"]


def test_an_unbound_form_is_never_recorded_at_an_other_declaration(tmp_path):
    """#918: the orchestrator's form is bound to nothing (its prose cites nothing), so a mismatch the judge names
    the runner's file for is no file the plan offered its check at: a warning, at the result's file."""
    tree = {"SKILL.md": f"# Demo\n\n{ORCHESTRATOR_FORM}.\n\n{APART}\n\n{LIGHTWEIGHT_LINE}\n"}
    mismatch = {**LIGHTWEIGHT_MISMATCH, "form": 0, "documented_sig": "(tasks=None, data=None, datasets=None)",
                "source_sig": "(steps, *, data=None, context=None) -> list", "issue": "another function"}
    out = _homonym_score(tmp_path, [mismatch], tree)
    assert [(m["file"], m["line"]) for m in out["mismatches"]] == [(ORCHESTRATOR, 37)]
    assert any(f"`{LIGHTWEIGHT}`, no file the plan offered its check at" in w for w in out["warnings"])


CONTRADICTED_RUNNER = {**LIGHTWEIGHT_MISMATCH, "difference": "annotation-contradicted",
                       "source_sig": "(steps, *, data=None, context=None) -> list",
                       "issue": "the annotation says `list`; the body returns the steps' results"}


@pytest.mark.parametrize("line, evidence, bound, severity, fact", [
    # the declaration line is the bound one, 37, whatever line the judge gives, so a body line after it holds it
    (40, 38, {"run_pipeline": {0: {"file": LIGHTWEIGHT, "line": 37}}}, "Info", None),
    (40, 38, {}, "Critical", "evidence_line 38 is before the declaration"),
    # another form bound in that file, at 60, bounds the first one's body
    (37, 62, {"run_pipeline": {0: {"file": LIGHTWEIGHT, "line": 37}}, "run_tasks": {0: {"file": LIGHTWEIGHT,
                                                                                      "line": 60}}},
     "Critical", "evidence_line 62 is not before the next declaration in the file, at line 60"),
    (37, 62, {"run_pipeline": {0: {"file": LIGHTWEIGHT, "line": 37}}}, "Info", None),
], ids=["declaration-line-from-the-binding", "unbound", "next-declaration-from-a-binding", "no-later-binding"])
def test_a_bound_declaration_locates_the_lines_a_record_would(line, evidence, bound, severity, fact):
    """#918: a bound form's declaration line is its bound declaration's, and a bound declaration bounds the body
    of the one before it in its file as a surface record does (no --source-root: the line order alone)."""
    offered = {"run_pipeline": [ORCHESTRATOR]}
    mismatch = {**CONTRADICTED_RUNNER, "line": line, "evidence_line": evidence, "form": 0}
    out = mod.score([_run_pipeline()[1]], ["run_pipeline"], [ORCHESTRATOR_RECORD],
                    [{"file": ORCHESTRATOR, "signature_mismatches": [mismatch]}], offered=offered, bound=bound)
    assert [(m["file"], m["severity"]) for m in out["mismatches"]] == [
        (LIGHTWEIGHT if bound else ORCHESTRATOR, severity)]
    found = [w for w in out["warnings"] if "tagged annotation-contradicted" in w]
    assert (len(found) == 1 and fact in found[0]) if fact else found == [], found


def test_a_bound_form_is_graded_at_its_declaration_and_keeps_its_own_mismatch():
    """#918: a bound form's file is the one it is graded at, so a parameter-name difference at a TS declaration is
    Low there; and of a check that offered several files, an unbound form keeps one mismatch, its closest, while a
    bound form keeps the one at its declaration."""
    renamed = {"name": "composeStories", "line": 40, "source_sig": "(csfExports: T, annotations?: Annotations)",
               "documented_sig": "(csfExports, projectAnnotations?)", "issue": "the second parameter is renamed",
               "difference": "parameter-name"}
    usage = {"name": "composeStories", "kind": "function", "usage_signature": "composeStories(stories)"}
    wrong = {"name": "composeStories", "line": 12, "source_sig": "(csfExports: T, annotations?: Annotations)",
             "documented_sig": "composeStories(stories)", "issue": "a call", "form": 1}
    offered = {"composeStories": [REACT, VUE]}
    out = mod.score([COMPOSE, usage], ["composeStories"], COMPOSE_RECORDS, [{"file": REACT, "signature_mismatches": [
        renamed, {**wrong, "file": VUE}, {**wrong, "file": REACT, "line": 40, "difference": "parameter-name"}]}],
                    offered=offered, bound={"composeStories": {0: {"file": VUE, "line": 12}}})
    assert [(m["file"], m["line"], m["severity"], m["documented_sig"]) for m in out["mismatches"]] == [
        (REACT, 40, "Low", "composeStories(stories)"), (VUE, 12, "Low", "(csfExports, projectAnnotations?)")]
    assert any(f"names `{REACT}`, but its form 0 is bound to the declaration at {VUE}:12" in w
               for w in out["warnings"]), out["warnings"]


def test_the_plan_s_bindings_are_read_by_form(tmp_path):
    """load_plan_bound reads each check's `bound`, by name then form index; an item with no index or no file
    binds nothing."""
    plan = {"files": [{"file": ORCHESTRATOR, "checks": [{"name": "run_pipeline", "bound": [
        ORCHESTRATOR_BOUND, LIGHTWEIGHT_BOUND, {"form": True, "file": LIGHTWEIGHT, "line": 1},
        {"form": 2, "file": "", "line": 1}, {"form": -1, "file": LIGHTWEIGHT}, "x"]}, {"name": "other"}]}]}
    assert mod.load_plan_bound(_write(tmp_path / "plan.json", plan)) == {
        "run_pipeline": {0: {"file": ORCHESTRATOR, "line": 53}, 1: {"file": LIGHTWEIGHT, "line": 37}}}


# #918 with a record that has no file: storybook's `createTest`, which an entry point passes on through a star
# re-export the runner gives no file. The declaration it reaches is an other declaration of the name.
PORTABLE = "code/core/src/preview-api/modules/store/csf/portable-stories.ts"
PORTABLE_COPY = "code/core/template/stories/portable-stories.ts"
CREATE_TEST = {"name": "createTest", "kind": "function", "params": "story: Story, annotations?: Annotations",
               "return_type": "Test", "at": "SKILL.md:3"}
FILELESS = {"exports": [{"name": "createTest", "kind": None, "file": None, "line": None, "signatureLine": None,
                         "origin": "extraction"}],
            "otherDeclarations": [
                {"name": "createTest", "kind": "function", "file": PORTABLE_COPY, "line": 5,
                 "signatureLine": "export function createTest("},
                {"name": "createTest", "kind": "function", "file": PORTABLE, "line": 319,
                 "signatureLine": "export function createTest("}],
            "sets": {"all": ["createTest"]}}


def test_a_form_of_a_record_with_no_file_is_bound_to_the_declaration_it_cites(tmp_path):
    """#918: the check of a name whose only record has no file stays at that record, in the "" group, and binds its
    form to the other declaration its citation names at its line, never the copy the skill cites elsewhere. A
    mismatch the judge finds there is recorded there, and that line bounds the evidence of an
    annotation-contradicted one. Without --skill-dir the check binds nothing, as before."""
    _write(tmp_path / "skill" / "SKILL.md",
           f"# Demo\n\n`createTest(story, annotations?)` builds a test [AST:{PORTABLE}:L319].\n\n"
           f"The template's createTest is a copy [SRC:{PORTABLE_COPY}:L40].\n")
    inventory = _write(tmp_path / "inventory.json", {"exports": [CREATE_TEST], "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", FILELESS)
    plan = tmp_path / "signature-plan.json"
    proc = _run("plan", "--inventory", inventory, "--surface", surface, "--skill-dir", str(tmp_path / "skill"),
                "--output", str(plan))
    assert proc.returncode == 0, proc.stderr
    documented = {"params": "story: Story, annotations?: Annotations", "return_type": "Test"}
    assert json.loads(proc.stdout)["files"] == [{"file": "", "checks": [{
        "name": "createTest", "line": None, "signatureLine": None, "documented": documented,
        "bound": [{"form": 0, "file": PORTABLE, "line": 319, "signatureLine": "export function createTest("}]}]}]
    without = json.loads(_run("plan", "--inventory", inventory, "--surface", surface).stdout)
    assert without["files"] == [{"file": "", "checks": [{
        "name": "createTest", "line": None, "signatureLine": None, "documented": documented}]}]
    mismatch = {"name": "createTest", "line": 325, "file": PORTABLE, "difference": "annotation-contradicted",
                "evidence_line": 322, "source_sig": "(story: Story, annotations?: Annotations): void",
                "documented_sig": "(story: Story, annotations?: Annotations): Test",
                "issue": "the annotation says `void`; the body returns the test"}
    results = _write(tmp_path / "s.txt", json.dumps({"file": PORTABLE, "signature_mismatches": [mismatch]}))
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--plan", str(plan),
                          "--results", results).stdout)
    # the declaration line is the bound one, 319, so the evidence at 322 is in its body
    assert [(m["file"], m["line"], m["severity"]) for m in out["mismatches"]] == [(PORTABLE, 319, "Info")]
    assert not any("createTest" in w for w in out["warnings"]), out["warnings"]
    assert (out["comparedNames"], out["totalDocumented"]) == (["createTest"], 1)
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--results", results).stdout)
    assert [(m["file"], m["severity"]) for m in out["mismatches"]] == [(PORTABLE, "Critical")]
    assert any("evidence_line 322 is before the declaration" in w for w in out["warnings"]), out["warnings"]


def test_a_form_bound_to_an_other_declaration_is_graded_at_its_file():
    """#918 review: a form bound to an other declaration is graded at that declaration's file. createTest's only
    record has no file, so the plan offers its check at none; bound to the TS declaration it cites, a renamed
    parameter there is Low, as at a TS file the plan offered. Unbound, the same mismatch is graded at the record's
    blank file: Critical."""
    renamed = {"name": "createTest", "line": 330, "file": PORTABLE, "difference": "parameter-name",
               "source_sig": "(story: Story, projectAnnotations?: Annotations): Test",
               "documented_sig": "(story: Story, annotations?: Annotations): Test",
               "issue": "the second parameter is `projectAnnotations`"}
    results = [{"file": PORTABLE, "signature_mismatches": [renamed]}]
    out = mod.score([CREATE_TEST], ["createTest"], FILELESS["exports"], results, offered={"createTest": [""]},
                    bound={"createTest": {0: {"file": PORTABLE, "line": 319}}})
    assert [(m["file"], m["line"], m["severity"]) for m in out["mismatches"]] == [(PORTABLE, 319, "Low")]
    assert (out["matchingSignatures"], out["totalDocumented"]) == (1, 1)
    out = mod.score([CREATE_TEST], ["createTest"], FILELESS["exports"], results, offered={"createTest": [""]})
    assert [m["severity"] for m in out["mismatches"]] == ["Critical"]


# #918 end to end: the cognee shape, a namespace member and a lazy `__getattr__` re-export of a same-named function,
# each declared at its line in cognee 1.6.2 (pipeline.py:53, run_pipeline.py:37).
HOMONYM_TREE = {
    "cognee/__init__.py": "from .modules import pipelines\n",
    "cognee/modules/__init__.py": "",
    "cognee/modules/pipelines/__init__.py": "from .operations.pipeline import run_pipeline\n",
    "cognee/modules/pipelines/operations/__init__.py": "",
    ORCHESTRATOR: "import asyncio\n" + "\n" * 51 + "async def run_pipeline(tasks=None, data=None, datasets=None):\n"
                  "    yield tasks\n",
    LIGHTWEIGHT: "import asyncio\n" + "\n" * 35 + "async def run_pipeline(steps, *, data=None, context=None) -> list:\n"
                 "    return [data]\n",
    "cognee/pipelines/__init__.py": ("def __getattr__(name):\n    if name == \"run_pipeline\":\n"
                                     "        from cognee.modules.pipelines.operations.run_pipeline import run_pipeline\n"
                                     "        return run_pipeline\n    raise AttributeError(name)\n"),
}
# The skill, shaped as oms-cognee 1.6.2 writes run_pipeline: a usage form citing the orchestrator, a prose form of
# the lightweight runner citing it (full-api-reference.md:264), the orchestrator's prose form citing it
# (full-api-reference.md:269), its fenced block, then the runner's fenced block followed by the citation the fix
# proposes (pipelines-and-datapoints.md:155 and :208) and its usage, which cites a range of the runner's body.
HOMONYM_SKILL_TREE = {
    "SKILL.md": (f"# Demo\n\n`async for _ in run_pipeline(tasks=tasks, data=text): pass` [SRC:{ORCHESTRATOR}:L53-L57]\n"),
    "references/api.md": (f"# API\n\n{LIGHTWEIGHT_LINE}\n\n"
                          "- `Task(executable)` wraps a callable [AST:cognee/modules/pipelines/tasks/task.py:L188]\n"
                          f"- `run_pipeline(tasks=None, data=None, datasets=None)`: the orchestrator "
                          f"[AST:{ORCHESTRATOR}:L53]\n"),
    "references/pipelines.md": ("## run_pipeline\n\n```python\nasync def run_pipeline(\n    tasks=None,\n"
                                "    data=None,\n    datasets=None,\n)\n```\n\n"
                                "Top-level async generator.\n\n"
                                "### Lightweight runner\n\n```python\nasync def run_pipeline(\n    steps,\n    *,\n"
                                "    data=None,\n    context=None,\n) -> list\n```\n\n"
                                f"`[AST:{LIGHTWEIGHT}:L37]`\n\n"
                                "```python\nresults = await run_pipeline([step()], data=raw)\n```\n\n"
                                f"- Each step gets the last one's output [SRC:{LIGHTWEIGHT}:L46-L61]\n"),
}
HOMONYM_INVENTORY = [
    {"name": "run_pipeline", "kind": "function", "usage_signature": "run_pipeline(tasks=tasks, data=text)",
     "description": "The orchestrator.", "at": "SKILL.md:3"},
    {"name": "run_pipeline", "kind": "function", "params": "steps, *, data=None, context=None", "return_type": "list",
     "description": "The lightweight runner.", "at": "references/api.md:3"},
    {"name": "run_pipeline", "kind": "function", "params": "tasks=None, data=None, datasets=None",
     "description": "The orchestrator.", "at": "references/api.md:6"},
    {"name": "run_pipeline", "kind": "function", "params": "tasks=None, data=None, datasets=None,",
     "description": "The orchestrator.", "at": "references/pipelines.md:4"},
    {"name": "run_pipeline", "kind": "function", "params": "steps, *, data=None, context=None,", "return_type": "list",
     "description": "The lightweight runner.", "at": "references/pipelines.md:16"},
    {"name": "run_pipeline", "kind": "function", "usage_signature": "run_pipeline([step()], data=raw)",
     "description": "The lightweight runner.", "at": "references/pipelines.md:27"},
]


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
def test_a_function_only_a_lazy_re_export_reaches_is_compared_where_its_form_cites_it(tmp_path):
    """#918 (oms-cognee run_pipeline) end to end: the runner gives the orchestrator as the `pipelines` namespace's
    member and records the lightweight runner only in exports[]; the surface lists it as an other declaration. The
    inventory gives each of the six forms its place, which validate-inventory.py checks against the skill, and the
    plan binds the three lightweight forms to run_pipeline.py:37 (the usage by its citation of the runner's body,
    L46-L61) and the orchestrator's cited forms to pipeline.py:53, while the check stays at the orchestrator. A
    mismatch the judge reports for a lightweight form is taken at run_pipeline.py:37."""
    source = tmp_path / "src"
    for rel, text in HOMONYM_TREE.items():
        _write(source / rel, text)
    extraction, surface = tmp_path / "extract-full.json", tmp_path / "surface.json"
    proc = subprocess.run([sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source),
                           "--scope-type", "public-api", "--tier", "Forge", "--head-cap", "0", "--output",
                           str(extraction)], capture_output=True, text=True, timeout=600)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    proc = subprocess.run([sys.executable, str(LOADER), "surface", "--extraction", str(extraction), "--output",
                           str(surface)], capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(surface.read_text(encoding="utf-8"))
    assert [(r["name"], r["file"], r["line"]) for r in data["exports"]] == [("run_pipeline", ORCHESTRATOR, 53)]
    assert [(d["name"], d["file"], d["line"]) for d in data["otherDeclarations"]] == [
        ("run_pipeline", LIGHTWEIGHT, 37)]
    skill = tmp_path / "skill"
    for rel, text in HOMONYM_SKILL_TREE.items():
        _write(skill / rel, text)
    response = _write(tmp_path / "inventory-response.txt", {
        "exports": HOMONYM_INVENTORY, "references": ["references/api.md", "references/pipelines.md"],
        "cross_check_mismatches": []})
    inventory = tmp_path / "inventory.json"
    proc = subprocess.run([sys.executable, str(SCRIPTS / "validate-inventory.py"), "--input", response,
                           "--skill-package", str(skill), "--output", str(inventory)], capture_output=True,
                          text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["warnings"] == [], "each of the six places writes the name"
    plan = tmp_path / "signature-plan.json"
    proc = _run("plan", "--inventory", str(inventory), "--surface", str(surface), "--skill-dir", str(skill),
                "--output", str(plan))
    assert proc.returncode == 0, proc.stderr
    [group] = json.loads(proc.stdout)["files"]
    [check] = group["checks"]
    assert (group["file"], check["line"], "candidates" in check) == (ORCHESTRATOR, 53, False)
    forms = [check["documented"], *check["alternatives"]]
    texts = [f.get("params") or f.get("usage_signature") for f in forms]
    assert texts == ["steps, *, data=None, context=None", "tasks=None, data=None, datasets=None",
                     "tasks=None, data=None, datasets=None,", "steps, *, data=None, context=None,",
                     "run_pipeline(tasks=tasks, data=text)", "run_pipeline([step()], data=raw)"]
    assert [(b["form"], b["file"], b["line"]) for b in check["bound"]] == [
        (0, LIGHTWEIGHT, 37), (1, ORCHESTRATOR, 53), (3, LIGHTWEIGHT, 37), (4, ORCHESTRATOR, 53), (5, LIGHTWEIGHT, 37)]
    mismatch = {**LIGHTWEIGHT_MISMATCH, "form": 3, "file": None, "line": 53,
                "documented_sig": "(steps, *, data=None, context=None,) -> list"}
    results = _write(tmp_path / "s.txt", json.dumps({"file": ORCHESTRATOR, "signature_mismatches": [mismatch]}))
    out = json.loads(_run("score", "--inventory", str(inventory), "--surface", str(surface), "--plan", str(plan),
                          "--results", results).stdout)
    assert [(m["file"], m["line"]) for m in out["mismatches"]] == [(LIGHTWEIGHT, 37)]
    assert [g["title"] for g in out["gapRecords"]] == ["Signature mismatch: run_pipeline (form 4 of 6)"]


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


def test_the_form_helpers_are_the_validators():
    """#888: validate-inventory.py's floor check reads a floor origin's form as this script tells two entries
    apart, so the helpers and the signature field list live there and this script reads them from it."""
    inventory = mod._inventory()
    assert "SIGNATURE_FIELDS = " not in SCRIPT.read_text(encoding="utf-8") and not hasattr(mod, "SIGNATURE_FIELDS")
    entry = {"name": "f", "kind": "function", "params": "a", "return_type": "R", "usage_signature": "f(a)",
             "description": "x", "signature_form": "partial"}
    assert list(mod._form(entry)) == [*inventory.SIGNATURE_FIELDS, "signature_form"]
    for value in (None, "a,\n  b", ["a", {"b": 1}], {"x": 2}, 3):
        assert mod._field_text(value) == inventory.field_text(value)
    fields = {"params": ["a", "b"], "return_type": "  ", "usage_signature": None, "signature_form": "partial"}
    assert mod._form_key(fields) == inventory.form_key(fields) == (("params", "a, b"),)


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
