#!/usr/bin/env python3
"""Tests for load-coverage-inputs.py (skf-test-skill coverage-check.md §0, §2, §2b; #613, #540).

coverage-check.md decides which denominator clause applies and whether a
bookkeeping variant is a real export; the script makes every count, the
surfaces of the Quick-tier and fallback per-file scans included (the
branches coverage-check.md §2 loads from coverage-check-tiers.md):
  - census: the docs-only verdict from the citation forms a skill writes
  - metadata: Cluster A and B under check-metadata-coherence.py's keys,
    the named-export count, the inflation signature and the declared names,
    and a stack's composition surface
  - surface: the source surface from a --mode full extraction (public names
    less those outside scope, never the recipes' internal matches), quick
    output, per-file results, names read by eye, or the provenance map and
    metadata (State 2 union and counts, the canonical fold over both), with
    the name sets, the Denominator Candidates, the guards and the fallback
    verdict; a brief gives the scope when no extraction recorded one, so a
    Quick-tier surface has its scope sets and guards too
  - surface, #677: an include glob that matches no file restores the root
    exports the brief does not exclude (the stale-scope guard), and a
    Python top nested in another top's folder is no barrel
The extraction fixture mirrors skf-extract-public-api.py --mode full output;
a last test runs the real extractor when ast-grep is installed.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "src" / "skf-test-skill" / "scripts"
SCRIPT = SCRIPTS / "load-coverage-inputs.py"
COHERENCE = SCRIPTS / "check-metadata-coherence.py"
COMPUTE_SCORE = SCRIPTS / "compute-score.py"
EXTRACTOR = REPO_ROOT / "src" / "shared" / "scripts" / "skf-extract-public-api.py"
GAP_LEDGER = SCRIPTS / "gap-ledger.py"
NUMERATOR = SCRIPTS / "verify-declared-numerator.py"
SCORE_SIGNATURES = SCRIPTS / "score-signatures.py"
RESOLVER = REPO_ROOT / "src" / "shared" / "scripts" / "skf-resolve-authoritative-files.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = _load(SCRIPT, "load_coverage_inputs")
gap_ledger = _load(GAP_LEDGER, "skf_gap_ledger_for_coverage_inputs")


def _write(path: Path, payload) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = payload if isinstance(payload, (bytes, str)) else json.dumps(payload)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return str(path)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8")


# A --mode full result: index.ts declares fetchData, Options and Mode and
# re-exports helper; extra.ts (a non-root `exports` subpath) declares Extra
# and Level; internalThing is a recipe match no entry point exports; legacy is
# exported but defined outside scope.include; gapFn is exported but no recipe
# found it.
EXTRACTION = {
    "mode": "full",
    "status": "ok",
    "files_in_scope": 3,
    "truncated": False,
    "files_without_recipes": {},
    "file_issues": [],
    "errors": [],
    "scope": {"include": ["src/**"], "exclude": ["src/vendor/**"], "tier_a_include": None,
              "type": "full-library", "languages": ["typescript"], "files_from": None},
    "exports": [
        {"export_name": "Extra", "export_type": "class", "source_file": "src/extra.ts", "source_line": 1,
         "signature_line": "export class Extra { run(): void {} }"},
        {"export_name": "Level", "export_type": "enum", "source_file": "src/extra.ts", "source_line": 2,
         "signature_line": "export enum Level { Low, High }"},
        {"export_name": "helper", "export_type": "function", "source_file": "src/helper.ts", "source_line": 1,
         "signature_line": "export function helper(x: number): number { return x; }"},
        {"export_name": "internalThing", "export_type": "function", "source_file": "src/helper.ts",
         "source_line": 2, "signature_line": "export function internalThing(): void {}"},
        {"export_name": "fetchData", "export_type": "function", "source_file": "src/index.ts", "source_line": 1,
         "signature_line": "export function fetchData(url: string): Promise<string> {"},
        {"export_name": "Options", "export_type": "interface", "source_file": "src/index.ts", "source_line": 2,
         "signature_line": "export interface Options { retries: number }"},
        {"export_name": "helper", "export_type": "re-export", "source_file": "src/index.ts", "source_line": 3,
         "signature_line": "export { helper } from './helper';"},
        {"export_name": "Mode", "export_type": "type", "source_file": "src/index.ts", "source_line": 4,
         "signature_line": "export type Mode = 'a' | 'b';"},
    ],
    "entry_points": {
        "status": "barrel",
        "files": [
            {"language": "typescript", "file": "src/index.ts", "package": ".", "subpath": ".",
             "resolution": "file", "in_scope": True},
            {"language": "typescript", "file": "src/extra.ts", "package": ".", "subpath": "./extra",
             "resolution": "file", "in_scope": True},
        ],
        "exports_maps": [], "unresolved": [],
    },
    "entry_point_diff": {
        "public": [
            {"name": "Extra", "entry": "src/extra.ts", "via": "declaration", "file": "src/extra.ts", "line": 1},
            {"name": "Level", "entry": "src/extra.ts", "via": "declaration", "file": "src/extra.ts", "line": 2},
            {"name": "Mode", "entry": "src/index.ts", "via": "declaration", "file": "src/index.ts", "line": 4},
            {"name": "Options", "entry": "src/index.ts", "via": "declaration", "file": "src/index.ts", "line": 2},
            {"name": "fetchData", "entry": "src/index.ts", "via": "declaration", "file": "src/index.ts", "line": 1},
            {"name": "gapFn", "entry": "src/index.ts", "via": "re-export", "file": "src/gap.ts", "line": 7},
            {"name": "helper", "entry": "src/index.ts", "via": "re-export", "file": "src/helper.ts", "line": 1},
            {"name": "legacy", "entry": "src/index.ts", "via": "re-export", "file": "lib/legacy.ts", "line": 3},
        ],
        "internal": [{"name": "internalThing", "language": "javascript", "source_file": "src/helper.ts",
                      "source_line": 2}],
        "extraction_gaps": [{"name": "gapFn", "language": "javascript", "entry": "src/index.ts",
                             "file": "src/gap.ts", "line": 7}],
        "outside_scope": [{"name": "legacy", "language": "javascript", "entry": "src/index.ts",
                           "file": "lib/legacy.ts", "line": 3}],
    },
    "counts": {"exports_public_api": 8, "exports_internal": 1, "effective_denominator": 7,
               "effective_denominator_basis": "scope.include", "denominator_files": 4},
    "arms": {"monorepo": False, "monorepo_kind": None, "specific_modules": False, "multi_subpath_exports": False},
}

METADATA = {
    "skill_type": "single",
    "exports": ["fetchData", "helper", "Options"],
    "stats": {"exports_public_api": 7, "exports_documented": 5, "effective_denominator": 4},
    "confidence_distribution": {"t1": 5, "t1_low": 0, "t2": 0, "t3": 0},
}

PROVENANCE = {"entries": [
    {"export_name": "fetchData", "export_type": "function", "source_file": "src/index.ts", "source_line": 1},
    {"export_name": "helper", "export_type": "function", "source_file": "src/helper.ts", "source_line": 1},
    {"export_name": "Extra::run", "export_type": "function"},
    {"export_name": "Button_def"},
    {"export_name": "Button"},
    {"export_name": "a11y_Checkbox"},
    {"export_name": "mobile_Card"},
    {"export_name": "Card"},
    {"export_name": "mobile_Orphan"},
]}


def _surface(tmp_path: Path, *args: str) -> dict:
    proc = _run("surface", *args, "--output", str(tmp_path / "surface.json"))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert json.loads((tmp_path / "surface.json").read_text(encoding="utf-8")) == out
    return out


# --------------------------------------------------------------------------
# census (#540, #613 item 4)
# --------------------------------------------------------------------------


def _skill(tmp_path: Path, body: str, refs: dict[str, str] | None = None) -> Path:
    root = tmp_path / "skill"
    _write(root / "SKILL.md", body)
    for name, text in (refs or {}).items():
        _write(root / "references" / name, text)
    return root


@pytest.mark.parametrize("body, refs, docs_only", [
    ("Use it [EXT:https://example.com/a]. Then [EXT:https://example.com/b].", {}, True),
    ("Use it [EXT:https://example.com/a] and `go()` [AST:src/a.ts:L3].", {}, False),
    ("Use it [EXT:https://example.com/a].", {"api.md": "`go()` [SRC:src/a.py:L9]"}, False),
    ("[from skill: liba] `connect()` and [EXT:https://example.com]", {}, False),
    ("No citation at all.", {}, False),
    ("[EXT:https://x.dev] [QMD:docs:intro] [DOC:readme]", {}, True),
], ids=["ext-only", "ext-and-ast", "src-in-a-reference", "stack-citation", "none", "qmd-decides-nothing"])
def test_census_decides_docs_only(tmp_path, body, refs, docs_only):
    root = _skill(tmp_path, body, refs)
    proc = _run("census", "--skill-dir", str(root))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["docsOnly"] is docs_only
    assert out["files"][0] == "SKILL.md"


def test_census_counts_each_form(tmp_path):
    root = _skill(tmp_path, "[EXT:a] [EXT:b] [AST:x:L1] [QMD:c:d]", {"r.md": "[SRC:y:L2] [from skill: z]"})
    out = mod.census(str(root))
    assert out["citations"] == {"EXT": 2, "AST": 1, "SRC": 1, "from skill": 1, "QMD": 1, "DOC": 0}
    assert out["localCitations"] == 3


def test_census_without_a_skill_md_exits_1(tmp_path):
    proc = _run("census", "--skill-dir", str(tmp_path))
    assert proc.returncode == 1 and "holds no SKILL.md" in proc.stderr and proc.stdout == ""


# --------------------------------------------------------------------------
# metadata (#613 item 3)
# --------------------------------------------------------------------------


def test_metadata_counts_feed_check_metadata_coherence(tmp_path):
    out = mod.metadata_inputs(METADATA, PROVENANCE)
    assert out["clusterA"] == {"exports_public_api": 7, "exports_length": 3}
    assert out["clusterB"] == {"exports_documented": 5}
    assert out["confidenceDistribution"] == {"t1": 5, "t1_low": 0, "t2": 0, "t3": 0}
    assert out["namedExports"]["count"] == 8 and "Extra::run" not in out["namedExports"]["names"]
    assert out["inflationSignature"] is False
    assert out["declaredNames"] == ["Options", "fetchData", "helper"]
    # check-metadata-coherence.py reads the same file by path.
    path = _write(tmp_path / "coverage-inputs.json", out)
    proc = subprocess.run([sys.executable, str(COHERENCE), "--inputs", path], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    coherence = json.loads(proc.stdout)
    assert coherence["clusterBCounts"] == {"stats.exports_documented": 5, "provenance named-exports": 8,
                                           "confidence_distribution sum": 5}


def test_metadata_flags_the_inflation_signature():
    meta = {**METADATA, "stats": {"exports_documented": 4, "effective_denominator": 4}}
    out = mod.metadata_inputs(meta, None)
    assert out["inflationSignature"] is True
    assert out["provenanceExportNames"] is None and out["namedExports"] is None


# #734: the map holds `foo` at src/a.ts and at src/b.ts (a name the entry points pass on from two files)
TWO_FILE_PROVENANCE = {"entries": [
    {"export_name": "foo", "export_type": "function", "source_file": "src/a.ts", "source_line": 1},
    {"export_name": "foo", "export_type": "function", "source_file": "src/b.ts", "source_line": 1},
    {"export_name": "bar", "export_type": "function", "source_file": "src/b.ts", "source_line": 2},
]}


# #734: a map whose `Foo` carries two `::` methods: two named exports, four distinct entry names
METHOD_PROVENANCE = {"entries": [{"export_name": name, "export_type": "function", "source_file": "src/foo.rs",
                                  "source_line": line}
                                 for line, name in enumerate(["Foo", "Foo::new", "Foo::run", "bar"], 1)]}
# `Foo` at two files beside `Foo::new` and `bar`: three distinct entry names, one of them a method
COINCIDENT_METHOD_PROVENANCE = {"entries": [
    {"export_name": "Foo", "export_type": "struct", "source_file": "src/a.rs", "source_line": 1},
    {"export_name": "Foo", "export_type": "struct", "source_file": "src/b.rs", "source_line": 1},
    {"export_name": "Foo::new", "export_type": "function", "source_file": "src/a.rs", "source_line": 2},
    {"export_name": "bar", "export_type": "function", "source_file": "src/a.rs", "source_line": 5},
]}
METHODS_ONLY_PROVENANCE = {"entries": [{"export_name": name, "export_type": "function"}
                                       for name in ("Foo::new", "Foo::run")]}


@pytest.mark.parametrize(("exports", "stats", "provenance", "signature", "named"), [
    (["foo", "bar"], {"exports_documented": 3, "effective_denominator": 2}, TWO_FILE_PROVENANCE, True, 2),
    (["foo", "bar"], {"exports_documented": 3, "effective_denominator": 3}, TWO_FILE_PROVENANCE, True, 2),
    (["foo", "bar"], {"exports_documented": 3, "effective_denominator": 4}, TWO_FILE_PROVENANCE, False, 2),
    (["foo", "bar"], {"effective_denominator": 2}, TWO_FILE_PROVENANCE, True, 2),
    (["Foo", "Foo::new", "Foo::run", "bar"], {"exports_documented": 4, "effective_denominator": 2},
     METHOD_PROVENANCE, False, 2),
    ([], {"effective_denominator": 0}, {"entries": []}, False, 0),
    (["foo", "bar"], {"exports_documented": 5}, PROVENANCE, False, 8),
    (["Foo", "bar", "baz"], {"exports_documented": 4, "effective_denominator": 3}, COINCIDENT_METHOD_PROVENANCE,
     False, 2),
    ([], {"effective_denominator": 2}, METHODS_ONLY_PROVENANCE, False, 0),
], ids=["two-entries-one-name", "documented-equals-the-count", "neither-equals", "no-documented-count",
        "method-entries", "empty-map", "no-stored-count", "method-entries-matching-by-chance", "methods-only"])
def test_the_inflation_signature_compares_the_stored_count_with_the_map_names_too(exports, stats, provenance,
                                                                                  signature, named):
    """#734: the stored count counts each name once and the map holds a name passed on from two files twice,
    so the signature fires when `stats.exports_documented` or the map's distinct entry names equal it. A map
    with a `::` entry never takes the map arm, even when its names match the stored count by chance, so a
    skill with methods behaves as before; an empty map fires nothing."""
    out = mod.metadata_inputs({"skill_type": "single", "exports": exports, "stats": stats}, provenance)
    assert out["inflationSignature"] is signature
    assert out["namedExports"]["count"] == named
    assert out["clusterB"] == {"exports_documented": stats.get("exports_documented")}


def test_the_map_arm_of_the_signature_runs_the_numerator_check_and_records_its_gap(tmp_path):
    """#734: a skill whose map holds `foo` at two files (3 entries, 2 names) stores 3 documented exports against
    a count of 2. The map's arm fires the signature, so verify-declared-numerator.py checks the declared names
    instead of reporting `skipped`, and the gap it raises claims neither that `stats.exports_documented` equals
    the denominator nor that it should be set by hand."""
    meta = _write(tmp_path / "skill" / "metadata.json", {"skill_type": "single", "exports": ["foo", "bar"],
                                                         "stats": {"exports_documented": 3,
                                                                   "effective_denominator": 2}})
    _write(tmp_path / "skill" / "SKILL.md", "# demo\n\n- `bar()`: returns nothing.\n")
    provenance = _write(tmp_path / "provenance-map.json", TWO_FILE_PROVENANCE)
    inputs = tmp_path / "run" / "coverage-inputs.json"
    proc = _run("metadata", "--metadata", meta, "--provenance", provenance, "--output", str(inputs))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["inflationSignature"] is True
    proc = subprocess.run([sys.executable, str(NUMERATOR), "--inputs", str(inputs), "--skill-dir",
                           str(tmp_path / "skill")], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    numerator = json.loads(proc.stdout)
    assert (numerator["skipped"], numerator["declared"], numerator["verified"], numerator["absent"],
            numerator["inflated"]) == (False, 2, 1, ["foo"], True)
    [gap] = gap_ledger.from_numerator(numerator, "skill/metadata.json")
    assert (gap["severity"], gap["category"], gap["source"]) == ("High", "numerator-inflation", "skill/metadata.json")
    assert gap["title"] == "numerator inflation: 1 of 2 declared exports absent from SKILL.md/references"
    assert gap["issue"] == ("a declared count (`stats.exports_documented`, or the provenance map's distinct entry "
                            "names) equals `stats.effective_denominator`, and these declared exports are absent "
                            "from SKILL.md and references/: `foo`")
    assert gap["remediation"] == ("Document the absent exports in SKILL.md or references/: the skill documents 1 "
                                  "of its 2 declared exports.")


def test_metadata_declared_names_fall_back_to_the_provenance_map():
    out = mod.metadata_inputs({"stats": {}}, PROVENANCE)
    assert "fetchData" in out["declaredNames"] and "Extra::run" not in out["declaredNames"]


def test_a_stack_denominator_comes_from_its_cited_contracts():
    meta = {"skill_type": "stack", "libraries": ["liba", "libb"], "integration_pairs": [["liba", "libb"]]}
    prov = {"entries": [{"export_name": "connect"}, {"export_name": "connect"}, {"export_name": "Client"},
                        {"export_name": "Client::new"}]}
    out = mod.metadata_inputs(meta, prov)
    assert out["stack"] == {"basis": "provenance", "denominator": 2, "compositionNames": ["Client", "connect"]}


def test_a_stack_without_a_map_counts_libraries_and_pairs():
    meta = {"skill_type": "stack", "libraries": ["liba", {"name": "libb"}],
            "integration_pairs": [["liba", "libb"], {"a": "libb", "b": "libc"}]}
    out = mod.metadata_inputs(meta, None)
    assert out["stack"] == {"basis": "composition", "denominator": 4,
                            "compositionNames": ["liba", "libb", "liba + libb", "libb + libc"]}


def test_metadata_cli_writes_the_file(tmp_path):
    meta = _write(tmp_path / "metadata.json", METADATA)
    out_path = tmp_path / "run" / "coverage-inputs.json"
    proc = _run("metadata", "--metadata", meta, "--output", str(out_path))
    assert proc.returncode == 0 and json.loads(out_path.read_text(encoding="utf-8")) == json.loads(proc.stdout)


def test_a_missing_metadata_file_exits_1(tmp_path):
    proc = _run("metadata", "--metadata", str(tmp_path / "absent.json"))
    assert proc.returncode == 1 and "cannot read --metadata" in proc.stderr


# --------------------------------------------------------------------------
# surface: a --mode full extraction (wave-3 determinism-1, determinism-5)
# --------------------------------------------------------------------------


def test_the_extraction_surface_is_the_public_names_less_outside_scope(tmp_path):
    extraction = _write(tmp_path / "extract-full.json", EXTRACTION)
    out = _surface(tmp_path, "--extraction", extraction)
    assert out["sets"]["all"] == ["Extra", "Level", "Mode", "Options", "fetchData", "gapFn", "helper"]
    assert "internalThing" not in out["sets"]["all"], "a recipe match no entry point exports is internal"
    assert out["excluded"]["outsideScope"] == [{"name": "legacy", "file": "lib/legacy.ts"}]
    assert out["extractionGaps"] == [{"name": "gapFn", "file": "src/gap.ts", "line": 7}]
    kinds = {e["name"]: e["kind"] for e in out["exports"]}
    # A re-export takes the kind recorded at the file that defines it.
    assert kinds == {"Extra": "class", "Level": "enum", "Mode": "type", "Options": "interface",
                     "fetchData": "function", "gapFn": None, "helper": "function"}
    helper = next(e for e in out["exports"] if e["name"] == "helper")
    assert (helper["file"], helper["line"]) == ("src/helper.ts", 1)
    assert out["extraction"]["fallback"] == {"needed": False, "reason": None}


def test_the_extraction_name_sets_and_candidates(tmp_path):
    extraction = _write(tmp_path / "extract-full.json", EXTRACTION)
    meta = _write(tmp_path / "metadata.json", METADATA)
    prov = _write(tmp_path / "provenance.json", PROVENANCE)
    out = _surface(tmp_path, "--extraction", extraction, "--metadata", meta, "--provenance", prov)
    # With an extraction the metadata and the map are baselines and add no name.
    assert out["sets"]["all"] == ["Extra", "Level", "Mode", "Options", "fetchData", "gapFn", "helper"]
    assert out["sets"]["scope.include"] == ["Extra", "Level", "Mode", "Options", "fetchData", "gapFn", "helper"]
    assert "tier_a_include" not in out["sets"]
    assert out["sets"]["subpaths"] == ["Extra", "Level"]
    assert out["sets"]["root"] == ["Mode", "Options", "fetchData", "gapFn", "helper", "legacy"]
    assert out["candidates"] == {"statsEffectiveDenominator": 4, "tierAIncludeUnion": None,
                                 "scopeIncludeUnion": 7, "subpathUnion": 2, "rootBarrel": 6,
                                 "extractorEffectiveDenominator": 7, "extractorBasis": "scope.include"}
    guards = out["guards"]
    assert guards["deflation"] == {"applicable": True, "effectiveDenominator": 4, "rederived": 7,
                                   "pct": 75.0, "fires": True}
    assert guards["inflation"] == {"applicable": True, "scopeIncludeUnion": 7, "provenanceEntries": 9,
                                   "pct": -22.22, "fires": False}
    assert guards["umbrella"]["ratio"] == 0.5 and guards["umbrella"]["umbrella"] is False
    assert out["state2"] is None


def test_a_tier_a_include_silences_both_guards(tmp_path):
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"]["tier_a_include"] = ["src/index.ts"]
    extraction = _write(tmp_path / "extract-full.json", data)
    meta = _write(tmp_path / "metadata.json", METADATA)
    prov = _write(tmp_path / "provenance.json", {"entries": [{"export_name": "x"}]})
    out = _surface(tmp_path, "--extraction", extraction, "--metadata", meta, "--provenance", prov)
    assert out["sets"]["tier_a_include"] == ["Mode", "Options", "fetchData"]
    assert out["guards"]["deflation"]["fires"] is False
    assert out["guards"]["inflation"]["applicable"] is False
    # #695: an extraction written before the runner listed unmatched tier A globs reads as listing none
    assert "unmatched_tier_a_include" not in data["scope"]
    assert out["guards"]["staleScope"] == {"applicable": True, "fires": False, "unmatchedInclude": [],
                                           "unmatchedTierAInclude": [], "restored": []}


def _stale_tier_a(tmp_path: Path, tier_a: list[str], unmatched: list[str], include: list[str] | None = None,
                  stats: dict | None = None) -> dict:
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"].update(tier_a_include=tier_a, unmatched_include=[], unmatched_tier_a_include=unmatched)
    if include is not None:
        data["scope"]["include"] = include
    data["warnings"] = [f"scope.tier_a_include pattern {g!r} matches no file" for g in unmatched]
    extraction = _write(tmp_path / "extract-full.json", data)
    meta = _write(tmp_path / "metadata.json", METADATA if stats is None else {**METADATA, "stats": stats})
    prov = _write(tmp_path / "provenance.json", {"entries": [{"export_name": "x"}]})
    return _surface(tmp_path, "--extraction", extraction, "--metadata", meta, "--provenance", prov)


def test_a_stale_tier_a_glob_counts_no_name(tmp_path):
    """#695: the runner lists one of the two tier A globs as matching no file. The stale-scope guard
    fires and names it, the set comes from the glob that matched, and that glob keeps both guards off."""
    # The loader never matches a glob itself: it trusts the runner's list, so the listed glob counts no
    # name even where a record's file would match it.
    out = _stale_tier_a(tmp_path, ["src/index.ts", "src/extra.ts"], ["src/extra.ts"])
    assert out["sets"]["tier_a_include"] == ["Mode", "Options", "fetchData"]
    assert out["candidates"]["tierAIncludeUnion"] == 3
    assert out["guards"]["staleScope"] == {"applicable": True, "fires": True, "unmatchedInclude": [],
                                           "unmatchedTierAInclude": ["src/extra.ts"], "restored": []}
    assert out["guards"]["deflation"]["fires"] is False
    assert out["guards"]["inflation"]["applicable"] is False
    assert out["warnings"] == ["extract-full.json: scope.tier_a_include pattern 'src/extra.ts' matches no file"]
    [record] = gap_ledger.from_guards(out)
    assert (record["category"], record["title"]) == (
        "brief-scope-stale", "stale brief scope: scope.tier_a_include globs match no source file")


def test_a_brief_with_only_stale_tier_a_globs_still_fires_the_guard(tmp_path):
    """#695: with no scope.include glob, a stale tier A glob alone makes the stale-scope guard apply and
    fire, and the ledger records one brief-scope-stale gap."""
    out = _stale_tier_a(tmp_path, ["src/old/**"], ["src/old/**"], include=[])
    stale = out["guards"]["staleScope"]
    assert (stale["applicable"], stale["fires"], stale["unmatchedTierAInclude"]) == (True, True, ["src/old/**"])
    records = [r for r in gap_ledger.from_guards(out) if r["category"] == "brief-scope-stale"]
    assert [r["title"] for r in records] == ["stale brief scope: scope.tier_a_include globs match no source file"]


def test_with_no_tier_a_glob_matching_both_guards_run(tmp_path):
    """#695: every tier A glob is stale, so surface.json has no tier_a_include set (the protocol and
    Type Coverage fall to the next set) and the deflation and inflation guards run and fire."""
    out = _stale_tier_a(tmp_path, ["src/old/**", "src/gone.ts"], ["src/old/**", "src/gone.ts"])
    assert "tier_a_include" not in out["sets"]
    assert out["candidates"]["tierAIncludeUnion"] is None
    assert out["guards"]["staleScope"]["fires"] is True
    assert out["guards"]["staleScope"]["unmatchedTierAInclude"] == ["src/old/**", "src/gone.ts"]
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 4, "rederived": 7,
                                          "pct": 75.0, "fires": True}
    assert out["guards"]["inflation"] == {"applicable": True, "scopeIncludeUnion": 7, "provenanceEntries": 1,
                                          "pct": 600.0, "fires": True}
    records = gap_ledger.from_guards(out)
    assert [r["category"] for r in records] == ["metadata-drift", "denominator-inflation", "brief-scope-stale"]
    assert all(r["issue"].endswith("and no `scope.tier_a_include` glob in the brief matches a file")
               for r in records[:2])
    assert out["guards"]["tierAInclude"] == ["src/old/**", "src/gone.ts"]


def test_a_stored_zero_is_deflation_not_a_denominator(tmp_path):
    """#712: a stratified skill whose Create Skill run stored an effective_denominator of 0 (every tier A glob
    stale) is deflation against the re-derived surface, with no percentage above 0, and the ledger gives one
    Medium metadata-drift gap that reads, not a 0-export halt."""
    out = _stale_tier_a(tmp_path, ["src/old/**"], ["src/old/**"], stats={"effective_denominator": 0})
    assert out["candidates"]["statsEffectiveDenominator"] == 0
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 0, "rederived": 7,
                                          "pct": None, "fires": True}
    records = gap_ledger.from_guards(out)
    drift = [r for r in records if r["category"] == "metadata-drift"]
    assert [(r["severity"], r["title"]) for r in drift] == [
        ("Medium", "denominator deflation: effective_denominator below source public surface without tier_a_include")]
    assert drift[0]["issue"] == (
        "the re-derived surface counts 7 exports against a `stats.effective_denominator` of 0, and no "
        "`scope.tier_a_include` glob in the brief matches a file")
    assert "brief-scope-stale" in [r["category"] for r in records]


def test_a_stored_zero_over_an_empty_surface_does_not_fire(tmp_path):
    """#712: with nothing re-derived there is nothing above the stored 0."""
    out = _stale_tier_a(tmp_path, ["src/old/**"], ["src/old/**"], include=["nothing/**"],
                        stats={"effective_denominator": 0})
    assert out["sets"]["scope.include"] == []
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 0, "rederived": 0,
                                          "pct": None, "fires": False}


def test_a_stored_zero_under_a_live_tier_a_set_does_not_fire(tmp_path):
    """#712 leaves this open on purpose: with a tier_a_include set the guard stays off, so a stored 0 is
    not deflation there."""
    out = _stale_tier_a(tmp_path, ["src/index.ts"], [], stats={"effective_denominator": 0})
    assert out["sets"]["tier_a_include"] == ["Mode", "Options", "fetchData"]
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 0, "rederived": 7,
                                          "pct": None, "fires": False}


@pytest.mark.parametrize("tier_a", [["lib/**"], ["src/vendor/**"], ["src/reexports.ts"]],
                         ids=["out-of-scope-only", "excluded-only", "nameless"])
def test_a_tier_a_list_that_counts_no_name_gives_no_set(tmp_path, tier_a):
    """#712: a live tier A glob whose files define no name in the surface (out of scope, excluded, or a barrel
    that only re-exports) counts no name either: no tier_a_include set, and both guards run."""
    out = _stale_tier_a(tmp_path, tier_a, [])
    assert "tier_a_include" not in out["sets"]
    assert out["candidates"]["tierAIncludeUnion"] is None
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 4, "rederived": 7,
                                          "pct": 75.0, "fires": True}
    assert out["guards"]["inflation"]["fires"] is True
    assert out["guards"]["staleScope"]["fires"] is False
    assert out["guards"]["tierAInclude"] == tier_a
    deflation, inflation = gap_ledger.from_guards(out)
    assert all(r["issue"].endswith("and no `scope.tier_a_include` glob in the brief counts a public name")
               for r in (deflation, inflation))
    assert inflation["remediation"].startswith("Edit `scope.tier_a_include`")


def test_a_tier_a_glob_over_a_named_re_export_from_outside_scope_gives_no_set(tmp_path):
    """#725: a name an in-scope barrel re-exports by name from a file scope.include leaves out has no
    outside_scope row, so it stays in the surface; a tier A name counts only in a file scope.include matches."""
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"]["tier_a_include"] = ["lib/gen.ts"]
    data["entry_point_diff"]["public"].append(
        {"name": "gen", "entry": "src/index.ts", "via": "re-export", "file": "lib/gen.ts", "line": 1})
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", data))
    assert "gen" in out["sets"]["all"] and "gen" not in out["sets"]["scope.include"]
    assert "tier_a_include" not in out["sets"]
    assert out["candidates"]["tierAIncludeUnion"] is None


def test_a_fallback_extraction_gives_only_its_scope_and_stale_globs(tmp_path):
    """#712: the fallback per-file scan passes the runner's exit-3 JSON beside its per-file results: its stale
    tier A glob counts no name and fires the stale-scope guard, the deflation guard runs on the per-file names,
    and the extraction adds no name and no `subpaths` or `root` set."""
    data = json.loads(json.dumps(EXTRACTION))
    data.update(status="no-ast-grep", exports=[], counts=None)
    data["scope"].update(tier_a_include=["src/old/**"], unmatched_include=[], unmatched_tier_a_include=["src/old/**"])
    data["warnings"] = ["scope.tier_a_include pattern 'src/old/**' matches no file",
                        "ast-grep is not on PATH: no recipe ran; extract by source reading"]
    per_file = _write(tmp_path / "per-file-1.txt", json.dumps({
        "file": "src/index.ts", "exports_found": ["fetchData", "Options"], "types_found": ["Options"],
        "signature_mismatches": []}))
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 1}})
    out = _surface(tmp_path, "--per-file", per_file, "--extraction", _write(tmp_path / "extract-full.json", data),
                   "--metadata", meta)
    assert out["extraction"]["fallback"] == {"needed": True, "reason": "no ast-grep the runner can run"}
    assert out["sets"] == {"all": ["Options", "fetchData"], "scope.include": ["Options", "fetchData"]}
    assert out["excluded"] == {"outsideScope": [], "nestedEntries": []} and out["extractionGaps"] == []
    assert out["guards"]["staleScope"] == {"applicable": True, "fires": True, "unmatchedInclude": [],
                                           "unmatchedTierAInclude": ["src/old/**"], "restored": []}
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 1, "rederived": 2,
                                          "pct": 100.0, "fires": True}
    assert out["guards"]["umbrella"] == mod.NO_UMBRELLA
    assert out["warnings"][0] == "extract-full.json: scope.tier_a_include pattern 'src/old/**' matches no file"


def test_a_namespace_gives_its_members_in_its_place(tmp_path):
    """#703: a namespace item (`export * as ns`, a Python submodule) stands for the names its module passes on,
    users' `pkg.ns.name`: each member joins the surface at the file that defines it, looked up by its `local` name
    there, with the namespace's entry; a member another public name has (same name and file) is listed once, one
    defined out of scope stays out with its outside_scope row, and a namespace the runner could not read stays."""
    extraction = json.loads(json.dumps(EXTRACTION))
    extraction["exports"].append({"export_name": "realFmt", "export_type": "function", "source_file": "src/ns/fmt.ts",
                                  "source_line": 2, "signature_line": "export function realFmt(): string {"})
    extraction["entry_point_diff"]["public"] += [
        {"name": "ns", "entry": "src/index.ts", "via": "namespace", "file": "src/ns/index.ts", "line": None,
         "members": [{"name": "fmt", "local": "realFmt", "file": "src/ns/fmt.ts", "line": 2},
                     {"name": "helper", "local": None, "file": "src/helper.ts", "line": 1},
                     {"name": "old", "local": None, "file": "lib/old.ts", "line": 9}]},
        {"name": "remote", "entry": "src/index.ts", "via": "namespace", "file": None, "line": None, "members": None}]
    extraction["entry_point_diff"]["outside_scope"].append(
        {"name": "old", "language": "javascript", "entry": "src/index.ts", "file": "lib/old.ts", "line": 9})
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", extraction))
    assert out["sets"]["all"] == ["Extra", "Level", "Mode", "Options", "fetchData", "fmt", "gapFn", "helper", "remote"]
    assert out["sets"]["root"] == ["Mode", "Options", "fetchData", "fmt", "gapFn", "helper", "legacy", "old", "remote"]
    fmt = [e for e in out["exports"] if e["name"] == "fmt"]
    assert [(e["kind"], e["file"], e["line"], e["signatureLine"]) for e in fmt] == [
        ("function", "src/ns/fmt.ts", 2, "export function realFmt(): string {")]
    assert [e["file"] for e in out["exports"] if e["name"] == "helper"] == ["src/helper.ts"]
    assert {"name": "old", "file": "lib/old.ts"} in out["excluded"]["outsideScope"]
    # the umbrella ratio counts the members too, each a re-export: the root's six names (gapFn, helper and legacy
    # re-exported) plus fmt and old, and remote, a namespace the runner could not read
    umbrella = out["guards"]["umbrella"]
    assert (umbrella["names"], umbrella["reexported"]) == (9, 6)


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
def test_a_real_namespace_feeds_its_members(tmp_path):
    """The #703 fixture through the runner: the surface is foo and sub's baz, never the module sub."""
    source = tmp_path / "src"
    for rel, text in (("pkg/__init__.py", "from .a import foo\nfrom . import sub\n"),
                      ("pkg/a.py", "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n"),
                      ("pkg/sub.py", "def baz():\n    return 4\n")):
        _write(source / rel, text)
    extraction = tmp_path / "run" / "extract-full.json"
    extraction.parent.mkdir()
    proc = subprocess.run([sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source),
                           "--scope-type", "public-api", "--head-cap", "0", "--output", str(extraction)],
                          capture_output=True, text=True)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    out = _surface(tmp_path, "--extraction", str(extraction))
    assert out["sets"]["all"] == ["baz", "foo"]
    assert {e["name"]: (e["kind"], e["file"], e["line"]) for e in out["exports"]} == {
        "baz": ("function", "pkg/sub.py", 1), "foo": ("function", "pkg/a.py", 1)}


def test_an_aliased_reexport_takes_the_kind_of_its_definition(tmp_path):
    """`export { Settings as Config } from './impl'`: the extractor records the
    export under the name impl.ts gives it, `local`."""
    data = json.loads(json.dumps(EXTRACTION))
    data["exports"].append({"export_name": "Settings", "export_type": "interface", "source_file": "src/impl.ts",
                            "source_line": 3, "signature_line": "export interface Settings {"})
    data["entry_point_diff"]["public"].append({"name": "Config", "entry": "src/index.ts", "via": "re-export",
                                               "local": "Settings", "file": "src/impl.ts", "line": 3})
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", data))
    config = next(e for e in out["exports"] if e["name"] == "Config")
    assert (config["kind"], config["line"], config["signatureLine"]) == (
        "interface", 3, "export interface Settings {")


@pytest.mark.parametrize("patch, reason", [
    ({"status": "no-ast-grep", "exports": []}, "no ast-grep the runner can run"),
    ({"files_in_scope": 0}, "no file in scope"),
    ({"files_without_recipes": {".java": 12}, "exports": []}, "no recipe reads the files in scope (.java)"),
], ids=["no-ast-grep", "nothing-in-scope", "no-recipe-for-the-language"])
def test_the_fallback_verdict(tmp_path, patch, reason):
    extraction = _write(tmp_path / "extract-full.json", {**EXTRACTION, **patch})
    out = _surface(tmp_path, "--extraction", extraction)
    assert out["extraction"]["fallback"] == {"needed": True, "reason": reason}


@pytest.mark.parametrize("brief_language, meta_language, needed", [
    (None, "java", True), ("Kotlin", "typescript", True), (None, "typescript", False), ("python", None, False),
    (None, None, False),
], ids=["metadata-java", "brief-kotlin-wins", "metadata-typescript", "brief-python", "no-language"])
def test_files_no_recipe_reads_in_the_skills_language_fall_back(tmp_path, brief_language, meta_language, needed):
    """A Java skill whose scope also matches a few JS files still needs the
    per-file scan: the recipes read only the JS files."""
    extraction = _write(tmp_path / "e.json", {**EXTRACTION, "files_without_recipes": {".java": 12}})
    args = ["--extraction", extraction]
    if meta_language:
        args += ["--metadata", _write(tmp_path / "metadata.json", {**METADATA, "language": meta_language})]
    if brief_language:
        args += ["--brief", _write(tmp_path / "skill-brief.yaml", f"name: demo\nlanguage: {brief_language}\n")]
    fallback = _surface(tmp_path, *args)["extraction"]["fallback"]
    assert fallback["needed"] is needed
    if needed:
        assert fallback["reason"] == (f"no recipe reads the skill's language, {brief_language or meta_language} "
                                      "(.java in scope)")


def test_an_incomplete_run_names_the_files_to_read_by_eye(tmp_path):
    patch = {"status": "incomplete",
             "file_issues": [{"file": "src/broken.ts", "issue": "syntax-errors", "count": 2, "line": 9},
                             {"file": "src/style.css", "issue": "no-recipes"}],
             "errors": [{"reason": "ast-grep-timeout", "files": 3, "first_file": "src/huge.ts", "detail": "x"}]}
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", {**EXTRACTION, **patch}))
    assert out["extraction"]["readByEye"] == ["src/broken.ts", "src/huge.ts"]
    assert out["extraction"]["fallback"]["needed"] is False


def test_an_incomplete_run_reads_by_eye_every_file_a_failed_call_lists_unread(tmp_path):
    """#722: a failed ast-grep call lists every file of its batch in `unread`, since a call cut while it prints can
    keep some of a file's exports and lose the rest: each of them is read by eye, not only the call's first file."""
    patch = {"status": "incomplete",
             "errors": [{"reason": "ast-grep-error", "files": 3, "first_file": "a.py", "detail": "exit 1: killed",
                         "unread": ["a.py", "b.py", "c.py"]}]}
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", {**EXTRACTION, **patch}))
    assert out["extraction"]["readByEye"] == ["a.py", "b.py", "c.py"]


def test_quick_mode_output_is_not_an_extraction(tmp_path):
    proc = _run("surface", "--extraction", _write(tmp_path / "q.json", {"exports": []}))
    assert proc.returncode == 1 and "--mode full" in proc.stderr


@pytest.mark.parametrize("path, pattern", [
    ("src/index.ts", "src/**"), ("src/a/b/c.ts", "src/**/*.ts"), ("src/index.ts", "src/**/*.ts"),
    ("test_x.py", "**/test_*"), ("a/test_x.py", "**/test_*"), ("src", "src/**"), ("srcx/a.ts", "src/**"),
    ("src/a.ts", "src/?.ts"), ("src/ab.ts", "src/?.ts"), ("src/a/b.ts", "src/*.ts"), ("lib/x.d.ts", "lib/*.d.ts"),
], ids=lambda v: v)
def test_the_glob_rule_is_the_extractors(path, pattern):
    resolver = _load(RESOLVER, "skf_resolve_authoritative_files_glob")
    assert mod.glob_match(path, pattern) == resolver.glob_match(path, pattern)


# --------------------------------------------------------------------------
# surface: a stale brief scope and nested Python tops (#677)
# --------------------------------------------------------------------------


# cognee v1.0.0 under a brief written for v0.5.8: pipelines.py became the
# pipelines/ package, so the brief's `cognee/pipelines.py` glob matches no
# file and the root re-exports run_pipeline and Task from files no glob
# covers; test_helper's file is excluded; the FastAPI routers/__init__.py is
# a top only because cognee/api/v1/ has no __init__.py. The shape is
# skf-extract-public-api.py's output on that tree (test_a_real_cognee_tree).
COGNEE_BRIEF = ("name: cognee\nlanguage: python\nscope:\n  type: public-api\n"
                "  include: ['cognee/__init__.py', 'cognee/pipelines.py', 'cognee/api/**']\n"
                "  exclude: ['cognee/tests/**']\n")
ROUTERS = "cognee/api/v1/routers/__init__.py"
ROUTER_NAMES = ["get_add_router", "get_search_router"]


def _public(name: str, entry: str, module: str, file: str, line: int = 1) -> dict:
    return {"name": name, "entry": entry, "via": "re-export", "from": module, "local": None, "file": file,
            "line": line, "language": "python"}


def _outside(name: str, file: str, line: int = 1, entry: str = "cognee/__init__.py") -> dict:
    return {"name": name, "language": "python", "entry": entry, "file": file, "line": line}


COGNEE = {
    "mode": "full",
    "status": "ok",
    "files_in_scope": 5,
    "truncated": False,
    "files_without_recipes": {},
    "file_issues": [],
    "errors": [],
    "scope": {"include": ["cognee/__init__.py", "cognee/pipelines.py", "cognee/api/**"],
              "exclude": ["cognee/tests/**"], "tier_a_include": None, "type": "public-api",
              "languages": ["python"], "files_from": None, "unmatched_include": ["cognee/pipelines.py"],
              "unmatched_tier_a_include": []},
    "exports": [
        {"export_name": "add", "export_type": "function", "source_file": "cognee/api/v1/add.py", "source_line": 1,
         "signature_line": "def add(data, dataset_name=\"main\"):"},
        {"export_name": "get_add_router", "export_type": "function", "source_file": "cognee/api/v1/routers/add.py",
         "source_line": 1, "signature_line": "def get_add_router():"},
        {"export_name": "get_search_router", "export_type": "function",
         "source_file": "cognee/api/v1/routers/search.py", "source_line": 1,
         "signature_line": "def get_search_router():"},
    ],
    "entry_points": {
        "status": "barrel",
        "files": [
            {"language": "python", "file": "cognee/__init__.py", "package": "cognee", "subpath": None,
             "resolution": "file", "in_scope": True},
            {"language": "python", "file": ROUTERS, "package": "cognee/api/v1/routers", "subpath": None,
             "resolution": "file", "in_scope": True},
        ],
        "exports_maps": [], "unresolved": [],
    },
    "entry_point_diff": {
        "public": [
            _public("Task", "cognee/__init__.py", ".pipelines", "cognee/pipelines/task.py", 2),
            _public("add", "cognee/__init__.py", ".api.v1.add", "cognee/api/v1/add.py"),
            _public("get_add_router", ROUTERS, ".add", "cognee/api/v1/routers/add.py"),
            _public("get_search_router", ROUTERS, ".search", "cognee/api/v1/routers/search.py"),
            _public("run_pipeline", "cognee/__init__.py", ".pipelines", "cognee/pipelines/run.py", 4),
            _public("test_helper", "cognee/__init__.py", ".tests.helper", "cognee/tests/helper.py"),
        ],
        "internal": [],
        "extraction_gaps": [],
        "outside_scope": [_outside("Task", "cognee/pipelines/task.py", 2),
                          _outside("run_pipeline", "cognee/pipelines/run.py", 4),
                          _outside("test_helper", "cognee/tests/helper.py")],
    },
    "counts": {"exports_public_api": 6, "exports_internal": 0, "effective_denominator": 3,
               "effective_denominator_basis": "scope.include", "denominator_files": 5},
    "arms": {"monorepo": False, "monorepo_kind": None, "specific_modules": False, "multi_subpath_exports": False},
    "warnings": ["scope.include pattern 'cognee/pipelines.py' matches no file"],
}
RESTORED = [{"name": "Task", "file": "cognee/pipelines/task.py", "line": 2},
            {"name": "run_pipeline", "file": "cognee/pipelines/run.py", "line": 4}]


def _cognee(tmp_path: Path, patch: dict | None = None, brief: str | None = COGNEE_BRIEF,
            data: dict | None = None) -> dict:
    data = json.loads(json.dumps(data or COGNEE))
    for key, value in (patch or {}).items():
        data["scope"][key] = value
    args = ["--extraction", _write(tmp_path / "extract-full.json", data)]
    if brief is not None:
        args += ["--brief", _write(tmp_path / "skill-brief.yaml", brief)]
    return _surface(tmp_path, *args)


def test_a_stale_glob_restores_the_root_exports_it_dropped(tmp_path):
    """The #677 acceptance: the re-exports come back to `all`, the routers'
    names leave it, and the ledger holds one brief-scope-stale gap."""
    out = _cognee(tmp_path)
    assert out["sets"]["all"] == ["Task", "add", "run_pipeline"]
    assert out["sets"]["scope.include"] == ["add", *ROUTER_NAMES], "a restored file matches no include glob"
    assert out["sets"]["root"] == ["Task", "add", "run_pipeline", "test_helper"]
    assert out["excluded"]["outsideScope"] == [{"name": "test_helper", "file": "cognee/tests/helper.py"}]
    assert out["guards"]["staleScope"] == {"applicable": True, "fires": True,
                                           "unmatchedInclude": ["cognee/pipelines.py"], "unmatchedTierAInclude": [],
                                           "restored": RESTORED}
    # No recipe reads a file out of scope, so a restored name has no kind: it
    # carries the file and line of its outside_scope row.
    restored = [e for e in out["exports"] if e["origin"] == "restored"]
    assert restored == [{"name": "Task", "kind": None, "file": "cognee/pipelines/task.py", "line": 2,
                         "signatureLine": None, "origin": "restored"},
                        {"name": "run_pipeline", "kind": None, "file": "cognee/pipelines/run.py", "line": 4,
                         "signatureLine": None, "origin": "restored"}]
    # The runner's warning text reaches the surface unchanged.
    assert out["warnings"] == ["extract-full.json: scope.include pattern 'cognee/pipelines.py' matches no file"]
    ledger = tmp_path / "test-findings-20261007T000000Z-abcdef12.json"
    proc = subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage",
                           "coverage-check", "--from", "guards", "--input", str(tmp_path / "surface.json")],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    records = json.loads(ledger.read_text(encoding="utf-8"))["records"]
    assert [(r["severity"], r["category"], r["source"]) for r in records] == [
        ("Medium", "brief-scope-stale", str(tmp_path / "skill-brief.yaml"))]
    assert records[0]["issue"] == (
        "the `scope.include` glob `cognee/pipelines.py` matches no file in the source tested; the `all` set "
        "restores 2 root exports, defined in files no include glob covers: `Task` in `cognee/pipelines/task.py`, "
        "`run_pipeline` in `cognee/pipelines/run.py`")


@pytest.mark.parametrize(("tier_a", "expected"), [(["cognee/pipelines/**"], None),
                                                  (["cognee/pipelines/**", "cognee/api/v1/add.py"], ["add"])],
                         ids=["restored-only", "restored-and-in-scope"])
def test_a_tier_a_glob_over_a_restored_file_counts_no_name(tmp_path, tier_a, expected):
    """#725: a restored name is back in `all`, but its file matches no include glob, so no tier A glob counts it."""
    out = _cognee(tmp_path, patch={"tier_a_include": tier_a})
    assert out["sets"]["all"] == ["Task", "add", "run_pipeline"]
    assert out["guards"]["staleScope"]["restored"] == RESTORED
    assert out["sets"].get("tier_a_include") == expected


def test_a_stale_tier_a_glob_joins_the_stale_scope_gap(tmp_path):
    """#695 end to end: the oms-cognee brief's old trace_context/** tier A glob beside a stale include
    glob is one Medium brief-scope-stale gap that names both, and the other tier A glob gives the set."""
    stale = "cognee/modules/observability/trace_context/**"
    out = _cognee(tmp_path, {"tier_a_include": ["cognee/api/**", stale], "unmatched_tier_a_include": [stale]})
    assert out["sets"]["tier_a_include"] == ["add", *ROUTER_NAMES]
    assert out["guards"]["staleScope"]["unmatchedTierAInclude"] == [stale]
    assert out["guards"]["staleScope"]["restored"] == RESTORED, "the include glob restores as before"
    ledger = tmp_path / "test-findings-20261009T000000Z-abcdef12.json"
    proc = subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage",
                           "coverage-check", "--from", "guards", "--input", str(tmp_path / "surface.json")],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    [record] = json.loads(ledger.read_text(encoding="utf-8"))["records"]
    assert (record["severity"], record["category"], record["title"]) == (
        "Medium", "brief-scope-stale",
        "stale brief scope: scope.include and scope.tier_a_include globs match no source file")
    assert record["issue"].startswith("the `scope.include` glob `cognee/pipelines.py` matches no file")
    assert record["issue"].endswith(
        f"; the `scope.tier_a_include` glob `{stale}` matches no file in the source tested, so it counts no name")


def test_a_nested_python_top_is_no_barrel(tmp_path):
    out = _cognee(tmp_path)
    assert not set(ROUTER_NAMES) & (set(out["sets"]["all"]) | set(out["sets"]["root"]))
    assert out["excluded"]["nestedEntries"] == [{"entry": ROUTERS, "within": "cognee/__init__.py",
                                                 "names": ROUTER_NAMES}]
    # The umbrella ratio counts the root barrel only: its four names, each a re-export.
    umbrella = out["guards"]["umbrella"]
    assert (umbrella["entries"], umbrella["names"], umbrella["reexported"]) == (["cognee/__init__.py"], 4, 4)
    # The records stay, with the kind and line the recipes gave them.
    kept = [(e["name"], e["kind"], e["file"], e["line"], e["origin"]) for e in out["exports"]
            if e["name"] in ROUTER_NAMES]
    assert kept == [("get_add_router", "function", "cognee/api/v1/routers/add.py", 1, "extraction"),
                    ("get_search_router", "function", "cognee/api/v1/routers/search.py", 1, "extraction")]


def test_a_documented_nested_name_keeps_its_signature_check(tmp_path):
    """A nested top's names leave `all`, yet score-signatures.py still plans
    and scores a documented one from its record: its wrong signature is a
    Critical gap, not a warning."""
    _cognee(tmp_path)
    surface = str(tmp_path / "surface.json")
    inventory = _write(tmp_path / "inventory.json", {"exports": [
        {"name": "add", "kind": "function", "params": "data, dataset_name", "return_type": "None"},
        {"name": "get_add_router", "kind": "function", "params": "", "return_type": "Router"},
    ], "cross_check_mismatches": []})
    plan = json.loads(subprocess.run([sys.executable, str(SCORE_SIGNATURES), "plan", "--inventory", inventory,
                                      "--surface", surface], capture_output=True, text=True, check=True).stdout)
    assert plan["compared"] == 2
    assert plan["files"][1] == {"file": "cognee/api/v1/routers/add.py", "checks": [
        {"name": "get_add_router", "line": 1, "signatureLine": "def get_add_router():",
         "documented": {"params": "", "return_type": "Router"}}]}
    mismatch = {"name": "get_add_router", "line": 1, "source_sig": "() -> APIRouter",
                "documented_sig": "() -> Router", "issue": "wrong return type"}
    results = _write(tmp_path / "signatures-1.txt", {"file": "cognee/api/v1/routers/add.py",
                                                      "signature_mismatches": [mismatch]})
    out = json.loads(subprocess.run([sys.executable, str(SCORE_SIGNATURES), "score", "--inventory", inventory,
                                     "--surface", surface, "--results", results],
                                    capture_output=True, text=True, check=True).stdout)
    assert (out["matchingSignatures"], out["totalDocumented"], out["signatureAccuracy"]) == (1, 2, 50.0)
    assert [(g["severity"], g["export"], g["source"]) for g in out["gapRecords"]] == [
        ("Critical", "get_add_router", "cognee/api/v1/routers/add.py:1")]
    assert out["warnings"] == ["the source surface has no interface, type alias, enum or class: Type "
                               "Coverage has nothing to cover and scores 100"]


def test_a_nested_top_keeps_its_names_in_the_scope_sets(tmp_path):
    """A specific-modules or stratified brief that scopes the sub-package in
    still counts it: a nested top leaves only `all`, `root` and the umbrella
    ratio, and a glob over its folder does not list its file."""
    out = _cognee(tmp_path, {"tier_a_include": ["cognee/api/v1/routers/**"]})
    assert out["sets"]["scope.include"] == ["add", *ROUTER_NAMES]
    assert out["sets"]["tier_a_include"] == ROUTER_NAMES
    assert (out["candidates"]["scopeIncludeUnion"], out["candidates"]["tierAIncludeUnion"]) == (3, 2)
    assert not set(ROUTER_NAMES) & set(out["sets"]["all"])
    assert [n["entry"] for n in out["excluded"]["nestedEntries"]] == [ROUTERS]


def test_a_nested_top_keeps_its_outside_scope_and_extraction_gap_rows(tmp_path):
    data = json.loads(json.dumps(COGNEE))
    diff = data["entry_point_diff"]
    diff["public"] += [_public("RouterConfig", ROUTERS, "..shared.config", "cognee/shared/config.py", 3),
                       _public("get_admin_router", ROUTERS, ".admin", "cognee/api/v1/routers/admin.py", 5)]
    diff["outside_scope"].append(_outside("RouterConfig", "cognee/shared/config.py", 3, entry=ROUTERS))
    diff["extraction_gaps"].append({"name": "get_admin_router", "language": "python", "entry": ROUTERS,
                                    "file": "cognee/api/v1/routers/admin.py", "line": 5})
    for rows in ("public", "outside_scope"):
        diff[rows].sort(key=lambda row: row["name"])  # the runner's order
    out = _cognee(tmp_path, data=data)
    assert out["excluded"]["outsideScope"] == [{"name": "RouterConfig", "file": "cognee/shared/config.py"},
                                               {"name": "test_helper", "file": "cognee/tests/helper.py"}]
    assert out["guards"]["staleScope"]["restored"] == RESTORED, "a nested top is no root entry point"
    assert out["extractionGaps"] == [{"name": "get_admin_router", "file": "cognee/api/v1/routers/admin.py",
                                      "line": 5}]
    assert out["excluded"]["nestedEntries"][0]["names"] == ["RouterConfig", "get_add_router", "get_admin_router",
                                                            "get_search_router"]
    assert out["sets"]["scope.include"] == ["add", "get_add_router", "get_admin_router", "get_search_router"]
    assert out["sets"]["all"] == ["Task", "add", "run_pipeline"]


@pytest.mark.parametrize("key", ["include", "tier_a_include"])
def test_a_nested_top_the_brief_names_stays_a_barrel(tmp_path, key):
    scope = json.loads(json.dumps(COGNEE["scope"]))
    out = _cognee(tmp_path, {key: (scope[key] or []) + [ROUTERS]})
    assert set(ROUTER_NAMES) <= set(out["sets"]["all"]) & set(out["sets"]["root"])
    assert out["excluded"]["nestedEntries"] == []


@pytest.mark.parametrize("amendments, restored", [
    ([("cognee/pipelines/**", "skipped", "scope-expansion", None)], []),
    ([("cognee/pipelines/run.py", "demoted-include", "scope-expansion", None)], RESTORED[:1]),
    ([("cognee/pipelines/**", "skipped", "scope-expansion", None),
      ("./cognee/pipelines/**", "promoted", "scope-expansion", None)], RESTORED),
    ([("cognee/pipelines/**", "skipped", "scope-expansion", "headless: no user to prompt")], RESTORED),
    ([("cognee/pipelines/**", "skipped", "auth-doc", None)], RESTORED),
], ids=["skipped", "demoted-include", "latest-wins", "legacy-headless-skip-is-a-deferral", "other-category"])
def test_a_declined_scope_expansion_keeps_its_file_out(tmp_path, amendments, restored):
    lines = "".join(f"    - path: '{path}'\n      action: {action}\n      category: {category}\n"
                    + (f"      reason: '{reason}'\n" if reason else "")
                    for path, action, category, reason in amendments)
    out = _cognee(tmp_path, brief=COGNEE_BRIEF + "  amendments:\n" + lines)
    assert out["guards"]["staleScope"]["restored"] == restored
    kept = {r["name"] for r in RESTORED} - {r["name"] for r in restored}
    assert [o["name"] for o in out["excluded"]["outsideScope"]] == sorted(kept | {"test_helper"})
    assert out["guards"]["staleScope"]["fires"] is True, "the glob is stale whatever the brief declined"


def test_an_excluded_file_stays_outside_scope(tmp_path):
    out = _cognee(tmp_path, {"exclude": ["cognee/tests/**", "cognee/pipelines/task.py"]})
    assert out["guards"]["staleScope"]["restored"] == RESTORED[1:]
    assert [o["name"] for o in out["excluded"]["outsideScope"]] == ["Task", "test_helper"]
    assert "Task" not in out["sets"]["all"]


def test_a_stale_glob_restores_root_exports_only(tmp_path):
    """A non-root `exports` subpath is no standard barrel: its outside_scope
    name stays out under a stale glob, while the root entry's comes back."""
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"].update(include=["src/**", "src/old.ts"], unmatched_include=["src/old.ts"])
    data["entry_point_diff"]["public"].append(
        {"name": "oldExtra", "entry": "src/extra.ts", "via": "re-export", "file": "lib/old-extra.ts", "line": 5})
    data["entry_point_diff"]["outside_scope"].append(
        {"name": "oldExtra", "language": "javascript", "entry": "src/extra.ts", "file": "lib/old-extra.ts",
         "line": 5})
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "extract-full.json", data))
    assert out["guards"]["staleScope"]["restored"] == [{"name": "legacy", "file": "lib/legacy.ts", "line": 3}]
    assert out["excluded"]["outsideScope"] == [{"name": "oldExtra", "file": "lib/old-extra.ts"}]
    assert "legacy" in out["sets"]["all"] and "oldExtra" not in out["sets"]["all"]


def test_a_fresh_brief_leaves_the_surface_unchanged(tmp_path):
    out = _cognee(tmp_path, {"unmatched_include": []})
    assert out["sets"]["all"] == ["add"]
    assert [o["name"] for o in out["excluded"]["outsideScope"]] == ["Task", "run_pipeline", "test_helper"]
    assert out["guards"]["staleScope"] == {"applicable": True, "fires": False, "unmatchedInclude": [],
                                           "unmatchedTierAInclude": [], "restored": []}
    assert gap_ledger.from_guards(out) == []


def test_without_a_brief_the_recorded_scope_still_decides(tmp_path):
    out = _cognee(tmp_path, brief=None)
    assert out["guards"]["staleScope"]["restored"] == RESTORED
    assert out["inputs"]["brief"] is None


def test_without_an_extraction_the_stale_scope_guard_does_not_apply(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", COGNEE_BRIEF)
    out = _surface(tmp_path, "--name", "add", "--brief", brief)
    assert out["guards"]["staleScope"] == {"applicable": False, "fires": False, "unmatchedInclude": [],
                                           "unmatchedTierAInclude": [], "restored": []}
    assert out["excluded"] == {"outsideScope": [], "nestedEntries": []}


@pytest.mark.parametrize("tops, silent, nested", [
    (["pkg/__init__.py", "pkg/a/routers/__init__.py"], [], {"pkg/a/routers/__init__.py": "pkg/__init__.py"}),
    (["ns/a/__init__.py", "ns/b/__init__.py"], [], {}),
    (["__init__.py", "sub/x/__init__.py"], [], {"sub/x/__init__.py": "__init__.py"}),
    (["pkg/__init__.py", "pkg/a/x/__init__.py", "pkg/a/x/b/y/__init__.py"], [],
     {"pkg/a/x/__init__.py": "pkg/__init__.py", "pkg/a/x/b/y/__init__.py": "pkg/__init__.py"}),
    (["pkg/__init__.py", "pkgx/a/__init__.py"], [], {}),
    (["pkg/__init__.py", "pkg/a/routers/__init__.py"], ["pkg/__init__.py"], {}),
    (["__init__.py", "pkg/__init__.py", "pkg/a/routers/__init__.py"], ["__init__.py"],
     {"pkg/a/routers/__init__.py": "pkg/__init__.py"}),
], ids=["nested", "siblings", "source-root-top", "outermost-holder", "prefix-is-not-a-folder",
        "outer-exports-nothing", "stray-source-root-init"])
def test_which_python_tops_are_nested(tops, silent, nested):
    """`silent` lists the tops that export no public name: such a top nests no other."""
    entries = [{"language": "python", "file": f, "subpath": None} for f in tops]
    assert mod._nested_tops(entries, set(), set(tops) - set(silent)) == nested


def test_a_stray_source_root_init_leaves_the_barrel_whole(tmp_path):
    """An empty __init__.py at the source root exports nothing, so it nests
    neither cognee/ nor its routers: the root barrel keeps its names, and the
    routers stay nested in cognee/__init__.py."""
    data = json.loads(json.dumps(COGNEE))
    data["entry_points"]["files"].insert(0, {"language": "python", "file": "__init__.py", "package": ".",
                                             "subpath": None, "resolution": "file", "in_scope": True})
    out = _cognee(tmp_path, data=data)
    assert out["sets"]["all"] == ["Task", "add", "run_pipeline"]
    assert out["sets"]["root"] == ["Task", "add", "run_pipeline", "test_helper"]
    assert out["excluded"]["nestedEntries"] == [{"entry": ROUTERS, "within": "cognee/__init__.py",
                                                 "names": ROUTER_NAMES}]
    assert out["guards"]["staleScope"]["restored"] == RESTORED


def test_sibling_tops_both_stay_barrels(tmp_path):
    data = {"mode": "full", "status": "ok", "files_in_scope": 2, "exports": [],
            "scope": {"include": ["ns/**"], "exclude": [], "tier_a_include": None, "unmatched_include": []},
            "entry_points": {"files": [
                {"language": "python", "file": "ns/a/__init__.py", "package": "ns/a", "subpath": None},
                {"language": "python", "file": "ns/b/__init__.py", "package": "ns/b", "subpath": None}]},
            "entry_point_diff": {"public": [
                {"name": "alpha", "entry": "ns/a/__init__.py", "via": "declaration", "file": "ns/a/__init__.py",
                 "line": 1},
                {"name": "beta", "entry": "ns/b/__init__.py", "via": "declaration", "file": "ns/b/__init__.py",
                 "line": 1}], "outside_scope": [], "extraction_gaps": []}}
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", data))
    assert out["sets"]["all"] == out["sets"]["root"] == ["alpha", "beta"]
    assert out["excluded"]["nestedEntries"] == []


def test_a_ts_entry_inside_the_root_entrys_folder_stays_a_barrel(tmp_path):
    """Only a Python top can be nested: a TypeScript entry point is a barrel
    wherever its folder lies."""
    data = {"mode": "full", "status": "ok", "files_in_scope": 2, "exports": [],
            "scope": {"include": ["pkg/**"], "exclude": [], "tier_a_include": None, "unmatched_include": []},
            "entry_points": {"files": [
                {"language": "python", "file": "pkg/__init__.py", "package": "pkg", "subpath": None},
                {"language": "typescript", "file": "pkg/ui/index.ts", "package": "pkg/ui", "subpath": "."}]},
            "entry_point_diff": {"public": [
                {"name": "alpha", "entry": "pkg/__init__.py", "via": "declaration", "file": "pkg/__init__.py",
                 "line": 1},
                {"name": "Widget", "entry": "pkg/ui/index.ts", "via": "declaration", "file": "pkg/ui/index.ts",
                 "line": 2}], "outside_scope": [], "extraction_gaps": []}}
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", data))
    assert out["sets"]["all"] == out["sets"]["root"] == ["Widget", "alpha"]
    assert out["excluded"]["nestedEntries"] == []
    entries = [{"language": "typescript", "file": f, "subpath": "."} for f in ("src/index.ts", "src/sub/index.ts")]
    assert mod._nested_tops(entries, set(), {"src/index.ts", "src/sub/index.ts"}) == {}


# --------------------------------------------------------------------------
# surface: the other sources
# --------------------------------------------------------------------------


def test_quick_output_and_names_read_by_eye(tmp_path):
    quick = _write(tmp_path / "quick-1.json", {"exports": [{"name": "fetchData", "type": "function",
                                                            "source_file": "src/index.ts"}],
                                               "warnings": ["src/index.ts:3: export * from './x'"]})
    out = _surface(tmp_path, "--quick", quick, "--name", "fromStar")
    assert out["sets"]["all"] == ["fetchData", "fromStar"]
    assert out["warnings"] == ["quick-1.json: src/index.ts:3: export * from './x'"]
    assert {e["origin"] for e in out["exports"]} == {"quick", "by-eye"}
    assert out["candidates"] is None and out["guards"] is None


def test_per_file_results_are_schema_checked(tmp_path):
    good = _write(tmp_path / "per-file-1.txt", "```json\n" + json.dumps({
        "file": "src/a.ts", "exports_found": ["a", "B"], "types_found": ["B"], "signature_mismatches": []}) + "\n```\n")
    out = _surface(tmp_path, "--per-file", good)
    assert out["sets"]["all"] == ["B", "a"]
    assert {e["name"]: e["kind"] for e in out["exports"]} == {"B": "type", "a": None}
    bad = _write(tmp_path / "per-file-2.txt", json.dumps({"file": "src/b.ts", "exports_found": "a"}))
    stale = tmp_path / "stale-surface.json"
    stale.write_bytes(b"{}")
    proc = _run("surface", "--per-file", good, "--per-file", bad, "--output", str(stale))
    # The breach exits 2 with the violations, as score-signatures.py does, so
    # the subagent can be re-dispatched with them.
    assert proc.returncode == 2, proc.stderr
    out = json.loads(proc.stdout)
    assert out["valid"] is False
    assert any(v.startswith("per-file-2.txt") and "signature_mismatches" in v for v in out["violations"])
    assert not stale.exists(), "a refused surface leaves no file for the next command to read"


# A curated brief at Quick tier: two packages of a monorepo, read by the
# quick parser; the brief scopes in core and api and names core's entry as
# its tier A surface.
BRIEF = ("name: demo\nlanguage: typescript\nscope:\n  type: specific-modules\n"
         "  include: ['packages/core/**', 'packages/api/**']\n  exclude: ['packages/api/internal/**']\n")


def _quick_monorepo(tmp_path: Path) -> list[str]:
    core = _write(tmp_path / "quick-1.json", {"exports": [
        {"name": n, "type": "function", "source_file": "packages/core/src/index.ts"}
        for n in ("connect", "query", "close")]})
    api = _write(tmp_path / "quick-2.json", {"exports": [
        {"name": "serve", "type": "function", "source_file": "packages/api/src/index.ts"},
        {"name": "route", "type": "function", "source_file": "packages/api/internal/router.ts"}]})
    cli = _write(tmp_path / "quick-3.json", {"exports": [
        {"name": "main", "type": "function", "source_file": "packages/cli/src/index.ts"}]})
    return ["--quick", core, "--quick", api, "--quick", cli]


def test_a_quick_tier_tier_a_glob_that_counts_no_name_gives_no_set(tmp_path):
    """#712: no empty tier_a_include set at Quick tier either; with no runner JSON the brief's glob still
    keeps the guards off (a quick name carries its entry file, not the file that defines it)."""
    brief = _write(tmp_path / "skill-brief.yaml", BRIEF + "  tier_a_include: ['packages/core/src/util/**']\n")
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 2}})
    prov = _write(tmp_path / "provenance.json", {"entries": [{"export_name": "x"}]})
    out = _surface(tmp_path, *_quick_monorepo(tmp_path), "--brief", brief, "--metadata", meta, "--provenance", prov)
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 2, "rederived": 4,
                                          "pct": 100.0, "fires": False}
    assert out["guards"]["inflation"]["applicable"] is False
    assert out["guards"]["tierAInclude"] == ["packages/core/src/util/**"]


# #733: the issue's fixture, `src/**` in scope. At Quick tier every name
# carries the entry file that exports it, so only a tier A glob whose
# folder or file differs from every scope.include glob's before any
# wildcard is known to count no name.
FX_BRIEF = "name: fx\nlanguage: typescript\nscope:\n  type: specific-modules\n  include: ['src/**']\n"
FX_PROVENANCE = {"entries": [{"export_name": n} for n in ("alpha", "beta", "gamma")]}


def _fx(tmp_path: Path, tier_a: str, stored: int, head: str = FX_BRIEF) -> list[str]:
    brief = _write(tmp_path / "skill-brief.yaml", head + f"  tier_a_include: ['{tier_a}']\n")
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": stored}})
    prov = _write(tmp_path / "provenance.json", FX_PROVENANCE)
    return ["--brief", brief, "--metadata", meta, "--provenance", prov]


def _fx_quick(tmp_path: Path) -> list[str]:
    return ["--quick", _write(tmp_path / "quick-1.json", {"exports": [
        {"name": n, "type": "function", "source_file": "src/index.ts"} for n in ("alpha", "beta", "gamma")]})]


@pytest.mark.parametrize(("tier_a", "include", "apart"), [
    ("gen/**", "src/**", True),
    ("packages/core/src/util/**", "packages/api/**", True),
    ("src/a.ts", "src/b.ts", True),
    ("src/*.ts", "lib/**", True),
    ("packages/core/src/util/**", "packages/core/**", False),
    ("src/b.ts", "src/**", False),
    ("**/gen/**", "src/**", False),
    ("s?c/gen/**", "src/**", False),
    ("src", "src/index.ts", False),
])
def test_two_globs_are_apart_when_a_literal_segment_differs_before_any_wildcard(tier_a, include, apart):
    """#733: two globs are apart when a literal segment differs before either has a `*` or `?`; any other
    pair counts as overlapping, even one no file can match both of (`src` beside `src/index.ts`), so the
    rule never drops a tier A glob that can count a name."""
    assert mod._apart(tier_a, include) is apart
    assert mod._apart(include, tier_a) is apart


@pytest.mark.parametrize(("tier_a", "exclude", "inside"), [
    ("src/gen/**", "src/gen/**", True),
    ("src/gen/extra.ts", "src/gen/**", True),
    ("src/gen/*.ts", "src/gen/**", True),
    ("src/b.ts", "src/b.ts", True),
    ("src/gen/**", "src/**", True),
    ("src/gen/**", "**/gen/**", True),
    ("src/gen/x.ts", "src/*/x.ts", True),
    ("src/gen", "src/gen/**", False),
    ("src/**", "src/gen/**", False),
    ("src/*/x.ts", "src/gen/**", False),
    ("src/g?n/**", "src/gen/**", False),
    ("src/gen/**", "src/gen/*", False),
    ("src/gen/x.ts", "src/gen/y.ts", False),
    ("gen/**", "**/gen/**", False),
])
def test_a_tier_a_glob_is_inside_an_exclude_glob_that_covers_it_segment_by_segment(tier_a, exclude, inside):
    """#749: a tier A glob is inside an exclude glob when, segment by segment, each of the exclude's is
    `**`, the same, or `*` beside one that is not `**`, with no segment of the tier A glob left over unless
    the exclude ends in `**`; any other pair counts as not inside, even one the exclude does cover (`gen/**`
    in `**/gen/**`), so the rule never drops a tier A glob that can count a name."""
    assert mod._inside(tier_a, exclude) is inside


def test_a_glob_inside_another_matches_no_path_the_other_misses():
    """#749: every pair `_inside` holds for, over globs of one to three segments, leaves no sampled path of
    one to four segments the tier A glob matches outside the exclude glob, by the extractor's own glob rule."""
    segments = ["src", "gen", "x.ts", "*", "**", "*.ts", "g?n"]
    globs = ["/".join(p) for n in (1, 2, 3) for p in itertools.product(segments, repeat=n)]
    names = ["src", "gen", "x.ts", "a"]
    paths = ["/".join(p) for n in (1, 2, 3, 4) for p in itertools.product(names, repeat=n)]
    for tier_a in globs:
        matched = [p for p in paths if mod.glob_match(p, tier_a)]
        for exclude in globs:
            if mod._inside(tier_a, exclude):
                assert all(mod.glob_match(p, exclude) for p in matched), (tier_a, exclude)


def test_a_quick_tier_tier_a_glob_outside_scope_include_runs_the_guards(tmp_path):
    """#733: `gen/**` beside `src/**` counts no name whatever the tree holds, so at Quick tier too it leaves
    the tier A list and both guards run; a glob inside `src/**` still keeps them off (#712)."""
    out = _surface(tmp_path, *_fx_quick(tmp_path), *_fx(tmp_path, "gen/**", 1))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 1, "rederived": 3,
                                          "pct": 200.0, "fires": True}
    assert out["guards"]["inflation"] == {"applicable": True, "scopeIncludeUnion": 3, "provenanceEntries": 3,
                                          "pct": 0.0, "fires": False}
    assert out["guards"]["tierAInclude"] == ["gen/**"], "the gap still names the brief's glob"
    [drift] = gap_ledger.from_guards(out)
    assert (drift["severity"], drift["category"]) == ("Medium", "metadata-drift")
    assert drift["issue"].endswith("and no `scope.tier_a_include` glob in the brief counts a public name")
    out = _surface(tmp_path, *_fx_quick(tmp_path), *_fx(tmp_path, "src/b.ts", 2))
    assert "tier_a_include" not in out["sets"], "no quick name carries src/b.ts"
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 2, "rederived": 3,
                                          "pct": 50.0, "fires": False}
    assert out["guards"]["inflation"]["applicable"] is False


@pytest.mark.parametrize("head", [
    "name: fx\nlanguage: typescript\nscope:\n  type: specific-modules\n  include: ['src/**', 'gen/**']\n",
    "name: fx\nlanguage: typescript\nscope:\n  type: specific-modules\n",
], ids=["an-include-glob-over-gen", "no-scope-include"])
def test_a_quick_tier_tier_a_glob_not_apart_from_every_include_glob_keeps_the_guards_off(tmp_path, head):
    """#733: `gen/**` leaves the list only when it is apart from every scope.include glob: beside a `gen/**`
    include, or with no scope.include at all, it stays, so at Quick tier the guards stay off (#712)."""
    out = _surface(tmp_path, *_fx_quick(tmp_path), *_fx(tmp_path, "gen/**", 1, head))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 1, "rederived": 3,
                                          "pct": 200.0, "fires": False}
    assert out["guards"]["inflation"]["applicable"] is False


# #749: an exclude that covers a tier A glob segment by segment leaves no file
# that glob can match, so at Quick tier too it counts no name.
FX_EXCLUDE = FX_BRIEF + "  exclude: ['src/gen/**']\n"


@pytest.mark.parametrize("tier_a", ["src/gen/**", "src/gen/extra.ts"])
def test_a_quick_tier_tier_a_glob_inside_a_scope_exclude_glob_runs_the_guards(tmp_path, tier_a):
    """#749: a tier A glob a scope.exclude glob covers counts no name whatever the tree holds, so at Quick tier
    it leaves the tier A list and both guards run, as at Forge tier."""
    out = _surface(tmp_path, *_fx_quick(tmp_path), *_fx(tmp_path, tier_a, 1, FX_EXCLUDE))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 1, "rederived": 3,
                                          "pct": 200.0, "fires": True}
    assert out["guards"]["inflation"] == {"applicable": True, "scopeIncludeUnion": 3, "provenanceEntries": 3,
                                          "pct": 0.0, "fires": False}
    assert out["guards"]["tierAInclude"] == [tier_a], "the gap still names the brief's glob"
    [drift] = gap_ledger.from_guards(out)
    assert (drift["severity"], drift["category"]) == ("Medium", "metadata-drift")
    assert drift["issue"].endswith("and no `scope.tier_a_include` glob in the brief counts a public name")


def _fx_globs(tmp_path: Path, exclude: list[str], tier_a: list[str]) -> list[str]:
    """`_fx` at a stored 1, with a list of scope.exclude globs and a list of tier A globs."""
    brief = _write(tmp_path / "skill-brief.yaml", FX_BRIEF + f"  exclude: {json.dumps(exclude)}\n"
                   f"  tier_a_include: {json.dumps(tier_a)}\n")
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 1}})
    prov = _write(tmp_path / "provenance.json", FX_PROVENANCE)
    return ["--brief", brief, "--metadata", meta, "--provenance", prov]


@pytest.mark.parametrize(("exclude", "tier_a", "fires"), [
    (["src/vendor/**", "src/gen/**"], ["src/gen/**"], True),
    (["src/gen/**"], ["src/gen/**", "gen/**"], True),
    (["src/gen/**"], ["src/gen/**", "src/b.ts"], False),
], ids=["inside-the-second-exclude-glob", "beside-a-glob-apart-from-scope-include",
        "beside-a-file-the-exclude-leaves"])
def test_a_quick_tier_tier_a_list_runs_the_guards_only_when_each_glob_leaves_it(tmp_path, exclude, tier_a,
                                                                                 fires):
    """#749: any scope.exclude glob can cover a tier A glob, and at Quick tier the guards run only when each
    glob leaves the list, inside an exclude glob or apart from every scope.include glob (#733)."""
    out = _surface(tmp_path, *_fx_quick(tmp_path), *_fx_globs(tmp_path, exclude, tier_a))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 1, "rederived": 3,
                                          "pct": 200.0, "fires": fires}
    assert out["guards"]["inflation"]["applicable"] is fires
    assert out["guards"]["tierAInclude"] == tier_a
    gaps = gap_ledger.from_guards(out)
    assert [(g["severity"], g["category"]) for g in gaps] == ([("Medium", "metadata-drift")] if fires else [])
    assert all(g["issue"].endswith("and no `scope.tier_a_include` glob in the brief counts a public name")
               for g in gaps)


@pytest.mark.parametrize(("tier_a", "tier_a_set"), [
    ("src/b.ts", None),
    ("src/**", ["alpha", "beta", "gamma"]),
    ("src/g?n/**", None),
], ids=["a-file-the-exclude-leaves", "the-include-glob", "a-wildcard-segment"])
def test_a_quick_tier_tier_a_glob_an_exclude_glob_does_not_cover_keeps_the_guards_off(tmp_path, tier_a,
                                                                                         tier_a_set):
    """#749: a tier A glob that can match a file the exclude leaves stays in the list, so at Quick tier the
    guards stay off (#712)."""
    out = _surface(tmp_path, *_fx_quick(tmp_path), *_fx(tmp_path, tier_a, 1, FX_EXCLUDE))
    assert out["sets"].get("tier_a_include") == tier_a_set
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 1, "rederived": 3,
                                          "pct": 200.0, "fires": False}
    assert out["guards"]["inflation"]["applicable"] is False


def test_a_provenance_surface_with_a_tier_a_glob_that_counts_no_name_gives_no_set(tmp_path):
    """#712: State 2 (and a pattern-reference app's map-only surface) has no empty tier_a_include set, so
    the canonicalized provenance map is the denominator."""
    prov = _write(tmp_path / "provenance.json", {"entries": PROVENANCE["entries"][:3]})
    brief = _write(tmp_path / "skill-brief.yaml", "scope:\n  include: ['src/**']\n  tier_a_include: ['src/old/**']\n")
    out = _surface(tmp_path, "--provenance", prov, "--brief", brief, "--fold")
    assert out["sets"] == {"all": ["fetchData", "helper"], "scope.include": ["fetchData", "helper"]}
    assert out["guards"]["deflation"]["applicable"] is False


def test_a_quick_tier_surface_takes_its_scope_from_the_brief(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", BRIEF + "  tier_a_include: ['packages/core/**']\n")
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 3}})
    out = _surface(tmp_path, *_quick_monorepo(tmp_path), "--brief", brief, "--metadata", meta)
    # metadata.json is a baseline here: its exports[] add no name.
    assert out["sets"]["all"] == ["close", "connect", "main", "query", "route", "serve"]
    assert out["sets"]["scope.include"] == ["close", "connect", "query", "serve"]
    assert out["sets"]["tier_a_include"] == ["close", "connect", "query"]
    assert "subpaths" not in out["sets"] and "root" not in out["sets"], "an extraction gives those"
    assert out["candidates"] == {"statsEffectiveDenominator": 3, "tierAIncludeUnion": 3, "scopeIncludeUnion": 4,
                                 "subpathUnion": None, "rootBarrel": None, "extractorEffectiveDenominator": None,
                                 "extractorBasis": None}
    assert out["guards"]["deflation"]["applicable"] is True and out["guards"]["deflation"]["fires"] is False
    assert out["guards"]["umbrella"]["umbrella"] is False
    # #695: with no runner JSON nothing says a tier A glob is stale: the brief's globs all count
    assert out["guards"]["staleScope"] == {"applicable": False, "fires": False, "unmatchedInclude": [],
                                           "unmatchedTierAInclude": [], "restored": []}


def test_the_deflation_guard_fires_at_quick_tier(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", BRIEF)
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 2}})
    out = _surface(tmp_path, *_quick_monorepo(tmp_path), "--brief", brief, "--metadata", meta)
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 2, "rederived": 4,
                                          "pct": 100.0, "fires": True}
    assert out["candidates"]["scopeIncludeUnion"] == 4


def test_per_file_results_carry_their_file_into_the_scope_sets(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", BRIEF)
    per_file = _write(tmp_path / "per-file-1.json", {"file": "packages/core/src/index.ts",
                                                     "exports_found": ["connect"], "signature_mismatches": []})
    out = _surface(tmp_path, "--per-file", per_file, "--name", "unplaced", "--brief", brief)
    assert out["sets"]["all"] == ["connect", "unplaced"]
    assert out["sets"]["scope.include"] == ["connect"], "a name with no file is in `all` only"


def _fx_fallback(tmp_path: Path) -> list[str]:
    """The fallback scan's results for the #733 fixture: each at the file that defines its names."""
    a = _write(tmp_path / "per-file-1.txt", {"file": "src/a.ts", "exports_found": ["alpha"], "types_found": [],
                                              "signature_mismatches": []})
    b = _write(tmp_path / "per-file-2.txt", {"file": "src/b.ts", "exports_found": ["beta", "gamma"],
                                              "types_found": [], "signature_mismatches": []})
    return ["--per-file", a, "--per-file", b]


@pytest.mark.parametrize("tier_a", ["src/gone/**", "src/types.ts", "gen/**"])
def test_a_fallback_scan_tier_a_list_that_counts_no_name_runs_the_guards(tmp_path, tier_a):
    """#733: with no runner JSON, --fallback-scan reads the per-file results as an extraction's records: a
    tier A list that gives no set (stale, over a file that defines no public name, or outside
    scope.include) narrows nothing, and the stale-scope guard still needs the runner's word."""
    out = _surface(tmp_path, *_fx_fallback(tmp_path), "--fallback-scan", *_fx(tmp_path, tier_a, 1))
    assert out["sets"] == {"all": ["alpha", "beta", "gamma"], "scope.include": ["alpha", "beta", "gamma"]}
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 1, "rederived": 3,
                                          "pct": 200.0, "fires": True}
    assert out["guards"]["inflation"] == {"applicable": True, "scopeIncludeUnion": 3, "provenanceEntries": 3,
                                          "pct": 0.0, "fires": False}
    assert out["guards"]["staleScope"]["applicable"] is False
    [drift] = gap_ledger.from_guards(out)
    assert (drift["severity"], drift["category"]) == ("Medium", "metadata-drift"), "no brief-scope-stale gap"
    assert drift["issue"].endswith("and no `scope.tier_a_include` glob in the brief counts a public name")


def test_a_fallback_scan_live_tier_a_glob_keeps_its_set_and_the_guards_off(tmp_path):
    """#733: a tier A glob over the file that defines two of the names gives a set, so the guards stay off."""
    out = _surface(tmp_path, *_fx_fallback(tmp_path), "--fallback-scan", *_fx(tmp_path, "src/b.ts", 2))
    assert out["sets"]["tier_a_include"] == ["beta", "gamma"]
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 2, "rederived": 3,
                                          "pct": 50.0, "fires": False}
    assert out["guards"]["inflation"]["applicable"] is False


@pytest.mark.parametrize("tier_a", ["src/gone/**", "src/types.ts", "src/b.ts"], ids=["stale", "nameless", "live"])
def test_per_file_results_without_fallback_scan_keep_the_glob_rule(tmp_path, tier_a):
    """#733: Quick tier's by-eye results and State 4's carry the entry file, not the defining one, so with no
    --fallback-scan a tier A glob inside scope.include that gives no set, stale or not, still keeps the
    guards off (#712)."""
    entry = _write(tmp_path / "per-file-1.json", {"file": "src/index.ts", "exports_found": ["alpha", "beta", "gamma"],
                                                  "signature_mismatches": []})
    out = _surface(tmp_path, "--per-file", entry, *_fx(tmp_path, tier_a, 2))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 2, "rederived": 3,
                                          "pct": 50.0, "fires": False}


def test_per_file_results_without_fallback_scan_drop_a_tier_a_glob_apart_from_scope_include(tmp_path):
    """#733: the glob rule leaves `gen/**` beside `src/**` out of the list for State 4's results too, so with
    no --fallback-scan the guards still run."""
    entry = _write(tmp_path / "per-file-1.json", {"file": "src/index.ts", "exports_found": ["alpha", "beta", "gamma"],
                                                  "signature_mismatches": []})
    out = _surface(tmp_path, "--per-file", entry, *_fx(tmp_path, "gen/**", 2))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 2, "rederived": 3,
                                          "pct": 50.0, "fires": True}
    assert out["guards"]["inflation"]["applicable"] is True


def test_per_file_results_without_fallback_scan_drop_a_tier_a_glob_inside_a_scope_exclude_glob(tmp_path):
    """#749: State 4's results carry the entry file too, so with no --fallback-scan a tier A glob a
    scope.exclude glob covers leaves the list and the guards run."""
    entry = _write(tmp_path / "per-file-1.json", {"file": "src/index.ts", "exports_found": ["alpha", "beta", "gamma"],
                                                  "signature_mismatches": []})
    out = _surface(tmp_path, "--per-file", entry, *_fx(tmp_path, "src/gen/**", 2, FX_EXCLUDE))
    assert "tier_a_include" not in out["sets"]
    assert out["guards"]["deflation"] == {"applicable": True, "effectiveDenominator": 2, "rederived": 3,
                                          "pct": 50.0, "fires": True}
    assert out["guards"]["inflation"]["applicable"] is True


def test_without_a_source_read_the_guards_do_not_run(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", BRIEF)
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 1}})
    out = _surface(tmp_path, "--metadata", meta, "--brief", brief)
    assert out["sets"]["all"] == ["Options", "fetchData", "helper"]
    assert "scope.include" not in out["sets"], "no metadata name carries a file"
    assert out["candidates"]["statsEffectiveDenominator"] == 1
    assert out["guards"]["deflation"]["applicable"] is False and out["guards"]["deflation"]["fires"] is False
    # #712: a stored 0 is no exception: with no source read there is nothing to re-derive
    _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 0}})
    deflation = _surface(tmp_path, "--metadata", meta, "--brief", brief)["guards"]["deflation"]
    assert (deflation["applicable"], deflation["pct"], deflation["fires"]) == (False, None, False)


def test_an_extraction_scope_wins_over_the_brief(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", "scope:\n  include: ['nothing/**']\n")
    out = _surface(tmp_path, "--extraction", _write(tmp_path / "e.json", EXTRACTION), "--brief", brief)
    assert out["sets"]["scope.include"] == out["sets"]["all"]


def test_a_brief_that_is_not_yaml_exits_1(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", "scope: [unclosed\n")
    proc = _run("surface", "--name", "x", "--brief", brief)
    assert proc.returncode == 1 and "is not valid YAML" in proc.stderr and proc.stderr.count("\n") == 1


def test_state_2_is_the_union_with_its_counts(tmp_path):
    meta = _write(tmp_path / "metadata.json", METADATA)
    prov = _write(tmp_path / "provenance.json", {"entries": PROVENANCE["entries"][:3]})
    out = _surface(tmp_path, "--provenance", prov, "--metadata", meta)
    assert out["sets"]["all"] == ["Options", "fetchData", "helper"]
    assert out["state2"] == {"provenanceCount": 2, "metadataCount": 3, "unionCount": 3,
                             "metadataOnly": ["Options"]}


def test_state_3_is_the_metadata_names(tmp_path):
    out = _surface(tmp_path, "--metadata", _write(tmp_path / "metadata.json", METADATA))
    assert out["sets"]["all"] == ["Options", "fetchData", "helper"] and out["state2"] is None


def test_the_canonical_fold(tmp_path):
    prov = _write(tmp_path / "provenance.json", PROVENANCE)
    out = _surface(tmp_path, "--provenance", prov, "--fold", "--fold-prefix", "mobile_", "--keep", "a11y_Checkbox")
    # Button_def folds to Button; mobile_Card folds to Card (Card is an entry);
    # mobile_Orphan stays (no Orphan entry); a11y_Checkbox is kept as a real export.
    assert out["sets"]["all"] == ["Button", "Card", "a11y_Checkbox", "fetchData", "helper", "mobile_Orphan"]
    canonical = out["canonical"]
    assert (canonical["raw"], canonical["canonical"]) == (8, 6)
    assert canonical["folded"] == {"_def": 1, "_exact": 0, "a11y_": 0, "other": 1}
    assert canonical["variants"] == {"Button_def": "Button", "mobile_Card": "Card"}
    assert canonical["summary"].startswith("Provenance-map canonicalization: 8 raw entries")


def test_the_fold_covers_the_metadata_names_too(tmp_path):
    """A variant folded out of the map never comes back through metadata.json,
    so two files listing the same names show no State 2 divergence."""
    names = [f"Widget{i}" for i in range(20)] + [f"Widget{i}_def" for i in range(5)]
    prov = _write(tmp_path / "provenance.json", {"entries": [{"export_name": n} for n in names]})
    meta = _write(tmp_path / "metadata.json", {"skill_type": "single", "exports": names})
    out = _surface(tmp_path, "--provenance", prov, "--metadata", meta, "--fold")
    assert out["sets"]["all"] == sorted(f"Widget{i}" for i in range(20))
    assert out["state2"] == {"provenanceCount": 20, "metadataCount": 20, "unionCount": 20, "metadataOnly": []}
    assert (out["canonical"]["raw"], out["canonical"]["canonical"]) == (25, 20)
    assert out["canonical"]["folded"]["_def"] == 5
    flags = {"mode": "naive", "tier": "Forge", "state2": True, "analysisConfidence": "provenance-map",
             "toolingStatus": "ok", "scores": {"exportCoverage": 90, "externalValidation": 80}}
    proc = subprocess.run([sys.executable, str(COMPUTE_SCORE), "--json-input", json.dumps(flags),
                           "--surface", str(tmp_path / "surface.json")], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    deduction = json.loads(proc.stdout)["state2Deduction"]
    assert (deduction["divergencePct"], deduction["applied"]) == (0.0, False)


def test_a_variant_only_metadata_lists_folds_to_a_map_base(tmp_path):
    prov = _write(tmp_path / "provenance.json", {"entries": [{"export_name": "Button"}, {"export_name": "Card"}]})
    meta = _write(tmp_path / "metadata.json", {"exports": ["Button", "Button_exact", "Card", "Extra"]})
    out = _surface(tmp_path, "--provenance", prov, "--metadata", meta, "--fold", "--keep", "Card")
    assert out["sets"]["all"] == ["Button", "Card", "Extra"]
    assert out["state2"] == {"provenanceCount": 2, "metadataCount": 3, "unionCount": 3, "metadataOnly": ["Extra"]}
    assert out["canonical"]["variants"] == {}, "the map itself held no variant"


def test_without_fold_no_variant_folds(tmp_path):
    out = _surface(tmp_path, "--provenance", _write(tmp_path / "provenance.json", PROVENANCE))
    assert "Button_def" in out["sets"]["all"] and out["canonical"] is None


def test_help_names_every_subcommand():
    proc = _run("--help")
    assert proc.returncode == 0
    for cmd in ("census", "metadata", "surface"):
        assert cmd in proc.stdout


# --------------------------------------------------------------------------
# A real --mode full run (needs ast-grep)
# --------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
def test_a_real_extraction_feeds_the_surface(tmp_path):
    source = tmp_path / "src"
    _write(source / "package.json", '{"name": "demo", "version": "1.0.0", "exports": {".": "./src/index.ts"}}\n')
    _write(source / "src" / "index.ts", "export function fetchData(url: string): string { return url; }\n"
                                        "export interface Options { retries: number }\n"
                                        "export { helper } from './helper';\n"
                                        "export { Settings as Config } from './impl';\n")
    _write(source / "src" / "helper.ts", "export function helper(x: number): number { return x; }\n"
                                         "export function internalThing(): void {}\n")
    _write(source / "src" / "impl.ts", "export interface Settings { depth: number }\n")
    brief = _write(tmp_path / "skill-brief.yaml", "name: demo\nlanguage: typescript\n"
                                                   "scope:\n  type: full-library\n  include: ['src/**']\n")
    extraction = tmp_path / "run" / "extract-full.json"
    extraction.parent.mkdir()
    proc = subprocess.run([sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source),
                           "--brief", brief, "--tier", "Forge", "--head-cap", "0", "--output", str(extraction)],
                          capture_output=True, text=True)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    out = _surface(tmp_path, "--extraction", str(extraction))
    assert out["sets"]["all"] == ["Config", "Options", "fetchData", "helper"]
    # Config is Settings re-exported under an alias: it keeps the kind and
    # line impl.ts defines it with.
    assert {e["name"]: e["kind"] for e in out["exports"]} == {"Config": "interface", "Options": "interface",
                                                              "fetchData": "function", "helper": "function"}
    config = next(e for e in out["exports"] if e["name"] == "Config")
    assert (config["file"], config["line"]) == ("src/impl.ts", 1)


COGNEE_TREE = {
    "cognee/__init__.py": "from .api.v1.add import add\nfrom .pipelines import run_pipeline, Task\n"
                          "from .tests.helper import test_helper\n",
    "cognee/pipelines/__init__.py": "from .run import run_pipeline\nfrom .task import Task\n",
    "cognee/pipelines/run.py": ("\"\"\"Run a pipeline.\"\"\"\n\n\n"
                                "def run_pipeline(tasks, data=None):\n    return tasks\n"),
    "cognee/pipelines/task.py": "# A pipeline step.\nclass Task:\n    pass\n",
    "cognee/api/v1/add.py": "def add(data, dataset_name=\"main\"):\n    return data\n",
    "cognee/api/v1/routers/__init__.py": "from .add import get_add_router\nfrom .search import get_search_router\n",
    "cognee/api/v1/routers/add.py": "def get_add_router():\n    return None\n",
    "cognee/api/v1/routers/search.py": "def get_search_router():\n    return None\n",
    "cognee/tests/helper.py": "def test_helper():\n    return 1\n",
}


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
def test_a_real_cognee_tree(tmp_path):
    """#677 end to end: the runner on the cognee v1.0.0 shape under its v0.5.8
    brief, then the surface: COGNEE above is this run's output."""
    source = tmp_path / "src"
    for rel, text in COGNEE_TREE.items():
        _write(source / rel, text)
    brief = _write(tmp_path / "skill-brief.yaml", COGNEE_BRIEF)
    extraction = tmp_path / "run" / "extract-full.json"
    extraction.parent.mkdir()
    proc = subprocess.run([sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source),
                           "--brief", brief, "--tier", "Forge", "--head-cap", "0", "--output", str(extraction)],
                          capture_output=True, text=True)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(extraction.read_text(encoding="utf-8"))
    assert data["scope"] == COGNEE["scope"]
    assert data["entry_points"]["files"] == COGNEE["entry_points"]["files"]
    assert data["entry_point_diff"] == COGNEE["entry_point_diff"]
    assert data["warnings"] == COGNEE["warnings"]
    out = _surface(tmp_path, "--extraction", str(extraction), "--brief", brief)
    assert out["sets"]["all"] == ["Task", "add", "run_pipeline"]
    assert out["sets"]["scope.include"] == ["add", *ROUTER_NAMES]
    assert out["guards"]["staleScope"]["restored"] == RESTORED
    assert [n["entry"] for n in out["excluded"]["nestedEntries"]] == [ROUTERS]


TIER_A_TREE = {
    "package.json": '{"name": "demo", "exports": {".": "./src/index.ts", "./macro": "./macro/index.ts"}}\n',
    "src/index.ts": "export { format } from './utils/format';\nexport const VERSION = '1';\n",
    "src/utils/format.ts": "export function format(v: string): string { return v; }\n",
    "macro/index.ts": "export function macro(): void {}\nexport interface MacroOptions { x: number }\n",
}


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
@pytest.mark.parametrize(("include", "tier_a", "basis", "count"),
                         [(["src/**"], ["macro/**"], "scope.include", 2),
                          (["src/**"], ["src/utils/**", "macro/**"], "tier_a_include", 1),
                          (["src/**"], ["src/utils/**"], "tier_a_include", 1),
                          ([], ["macro/**"], "tier_a_include", 2)],
                         ids=["outside-only", "mixed", "inside-only", "no-include"])
def test_the_runner_and_the_surface_count_one_tier_a_set(tmp_path, include, tier_a, basis, count):
    """#725: the count Create Skill stores is the one Test Skill re-derives: the runner's tier A count is the
    tier_a_include set, and when it falls back to scope.include the surface has no set."""
    source = tmp_path / "src"
    for rel, text in TIER_A_TREE.items():
        _write(source / rel, text)
    extraction = tmp_path / "run" / "extract-full.json"
    extraction.parent.mkdir()
    argv = [sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source),
            "--tier", "Forge", "--head-cap", "0", "--output", str(extraction)]
    for glob in include:
        argv += ["--include", glob]
    for glob in tier_a:
        argv += ["--tier-a-include", glob]
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    counts = json.loads(extraction.read_text(encoding="utf-8"))["counts"]
    out = _surface(tmp_path, "--extraction", str(extraction))
    assert counts["effective_denominator_basis"] == basis
    if basis == "tier_a_include":
        assert counts["effective_denominator"] == out["candidates"]["tierAIncludeUnion"] == count
    else:
        assert "tier_a_include" not in out["sets"]
        assert counts["effective_denominator"] == out["candidates"]["scopeIncludeUnion"] == count


# #734: `foo` at src/a.ts and, through `export * as ns`, at src/b.ts beside `bar`: two records, one name
TWO_FILE_TREE = {
    "package.json": '{"name": "demo", "exports": {".": "./src/index.ts"}}\n',
    "src/index.ts": "export { foo } from './a';\nexport * as ns from './b';\n",
    "src/a.ts": "export function foo(): number { return 1; }\n",
    "src/b.ts": "export function foo(): string { return ''; }\nexport function bar(): void {}\n",
}


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is not installed")
@pytest.mark.parametrize(("flags", "basis", "union", "records", "count"), [
    (["--tier-a-include", "src/**"], "tier_a_include", "tierAIncludeUnion",
     [("bar", "src/b.ts"), ("foo", "src/a.ts"), ("foo", "src/b.ts")], 2),
    ([], "scope.include", "scopeIncludeUnion", [("bar", "src/b.ts"), ("foo", "src/a.ts"), ("foo", "src/b.ts")], 2),
    (["--exclude", "src/b.ts"], "scope.include", "scopeIncludeUnion", [("foo", "src/a.ts")], 1),
    (["--tier-a-include", "src/a.ts"], "tier_a_include", "tierAIncludeUnion",
     [("bar", "src/b.ts"), ("foo", "src/a.ts"), ("foo", "src/b.ts")], 1),
], ids=["tier-a", "scope-include", "one-key-excluded", "tier-a-a-only"])
def test_the_runner_counts_a_name_passed_on_from_two_files_once_as_the_surface_does(tmp_path, flags, basis, union,
                                                                                    records, count):
    """#734: the count Create Skill stores is the set Test Skill re-derives when the entry points pass one
    name on from two files: the runner counts it once, while the surface keeps a record (a signature) for each.
    With src/b.ts excluded, or a tier A list of src/a.ts alone, `foo` still counts once, by its key at src/a.ts."""
    source = tmp_path / "src"
    for rel, text in TWO_FILE_TREE.items():
        _write(source / rel, text)
    extraction = tmp_path / "run" / "extract-full.json"
    extraction.parent.mkdir()
    argv = [sys.executable, str(EXTRACTOR), "--mode", "full", "--source-root", str(source), "--include", "src/**",
            *flags, "--tier", "Forge", "--head-cap", "0", "--output", str(extraction)]
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode == 3:
        pytest.skip("the extractor found no ast-grep it can run")
    assert proc.returncode == 0, proc.stderr
    counts = json.loads(extraction.read_text(encoding="utf-8"))["counts"]
    out = _surface(tmp_path, "--extraction", str(extraction))
    assert [(r["name"], r["file"]) for r in out["exports"]] == records
    assert (counts["exports_public_api"], counts["effective_denominator_basis"]) == (3, basis)
    candidates = out["candidates"]
    assert counts["effective_denominator"] == candidates[union] == candidates["extractorEffectiveDenominator"] == count
    assert len(out["sets"][basis]) == count
