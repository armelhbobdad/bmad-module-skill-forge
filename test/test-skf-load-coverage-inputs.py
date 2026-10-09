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


def _stale_tier_a(tmp_path: Path, tier_a: list[str], unmatched: list[str], include: list[str] | None = None) -> dict:
    data = json.loads(json.dumps(EXTRACTION))
    data["scope"].update(tier_a_include=tier_a, unmatched_include=[], unmatched_tier_a_include=unmatched)
    if include is not None:
        data["scope"]["include"] = include
    data["warnings"] = [f"scope.tier_a_include pattern {g!r} matches no file" for g in unmatched]
    extraction = _write(tmp_path / "extract-full.json", data)
    meta = _write(tmp_path / "metadata.json", METADATA)
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


def test_without_a_source_read_the_guards_do_not_run(tmp_path):
    brief = _write(tmp_path / "skill-brief.yaml", BRIEF)
    meta = _write(tmp_path / "metadata.json", {**METADATA, "stats": {"effective_denominator": 1}})
    out = _surface(tmp_path, "--metadata", meta, "--brief", brief)
    assert out["sets"]["all"] == ["Options", "fetchData", "helper"]
    assert "scope.include" not in out["sets"], "no metadata name carries a file"
    assert out["candidates"]["statsEffectiveDenominator"] == 1
    assert out["guards"]["deflation"]["applicable"] is False and out["guards"]["deflation"]["fires"] is False


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
