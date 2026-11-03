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
HARD_GATE = SCRIPTS / "hard-gate.py"

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


@pytest.mark.parametrize("payload, needle", [
    ("not json", "not valid JSON"),
    ({"signature_mismatches": []}, "`file` must be a non-empty string"),
    ({"file": "a.ts"}, "`signature_mismatches` must be present"),
    ({"file": "a.ts", "signature_mismatches": [{"name": "x"}]}, "missing field(s)"),
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "line": "1"}]}, "`line` must be a line number"),
    ({"file": "a.ts", "exports_found": "x", "signature_mismatches": []}, "`exports_found` must be a list"),
    # #793: a difference outside the enum is refused, the field named
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "difference": "bogus"}]},
     'signature_mismatches[0]: `difference` must be one of parameter-name, omitted-optional when present, '
     'not "bogus"'),
], ids=["not-json", "no-file", "no-mismatches", "missing-fields", "line-not-int", "exports-not-list",
        "bad-difference"])
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
