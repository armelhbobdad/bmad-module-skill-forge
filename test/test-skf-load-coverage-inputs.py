#!/usr/bin/env python3
"""Tests for load-coverage-inputs.py (skf-test-skill coverage-check.md §0, §2, §2b; #613, #540).

coverage-check.md decides which denominator clause applies and whether a
bookkeeping variant is a real export; the script makes every count:
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
RESOLVER = REPO_ROOT / "src" / "shared" / "scripts" / "skf-resolve-authoritative-files.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = _load(SCRIPT, "load_coverage_inputs")


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
