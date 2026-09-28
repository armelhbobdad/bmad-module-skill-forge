#!/usr/bin/env python3
"""Tests for skf-verify-provenance-completeness.py.

Covers:
  - extract_export_names: string items, dict items, non-string skips
  - extract_reexport_map / canon: top-level + per-entry, idempotence
  - check_citation: valid, file-missing, line-out-of-bounds, line-invalid,
    null-tolerated
  - resolve_source_root: override wins, provenance fallback, None when absent
  - verify end-to-end:
      * single-skill fixture — missing==[C], orphaned==[D], stale B is
        line-out-of-bounds, null-citation E tolerated, summary counts
      * stack-skill fixture — reexport_map canonicalization collapses an
        internal-named entry, plus a file-missing stale reason
      * skipped stale check when no source root resolves
  - definition lines (#530 AC 2): a line one early (blank above an
    `async def`) and a line inside a three-line decorator get
    `line-not-definition` with the def line; exact lines, import aliases,
    parenthesized imports, assignments and dotted names pass; TS/JS
    declarations and `export { ... }` lists; `module` / `package` entries
    and other languages are skipped and counted; the older reasons win
  - shapes added in review pass 1: TS class members for dotted names (calls
    excluded), CommonJS exports, `namespace`, `export import`, `export * as`,
    `export default NAME`, Python try-block, annotation-only, target-list,
    chained and PEP 695 assignments, backslash imports, BOM and CRLF files,
    the column-0 rule for local shadows, docstring / keyword-argument lines
    that never match, and a barrel-internal name
  - citation prefixes with `--skill-dir` (#530 AC 3): `prefix-mismatch`,
    `ast-without-ast-grep`, ranges, ignored line-less citations, ordering,
    `ast_bridge` / `source_reading`, a non-string method,
    `skill_citations_matched`
  - CLI smoke: exit 0 clean, exit 1 findings, exit 2 on bad input (including
    a `--skill-dir` with no SKILL.md)
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = (
    REPO_ROOT
    / "src"
    / "shared"
    / "scripts"
    / "skf-verify-provenance-completeness.py"
)

spec = importlib.util.spec_from_file_location(
    "skf_verify_provenance_completeness", SCRIPT_PATH
)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_source(
    root: Path, rel: str, lines: int, defs: dict[int, str] | None = None
) -> Path:
    """Write `lines` filler lines; `defs` puts real source text at given lines."""
    defs = defs or {}
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(defs.get(i, f"// line {i}") for i in range(1, lines + 1)),
        encoding="utf-8",
    )
    return p


def _write_text(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# extract_export_names
# --------------------------------------------------------------------------


class TestExtractExportNames:
    def test_string_list(self) -> None:
        assert mod.extract_export_names({"exports": ["A", "B"]}) == ["A", "B"]

    def test_dict_items(self) -> None:
        meta = {"exports": [{"name": "A"}, {"export_name": "B"}]}
        assert mod.extract_export_names(meta) == ["A", "B"]

    def test_skips_empty_and_non_string(self) -> None:
        meta = {"exports": ["A", "", 42, None, {"name": ""}, {"nope": "x"}]}
        assert mod.extract_export_names(meta) == ["A"]

    def test_missing_exports_key(self) -> None:
        assert mod.extract_export_names({}) == []

    def test_exports_not_list(self) -> None:
        assert mod.extract_export_names({"exports": "A"}) == []


# --------------------------------------------------------------------------
# extract_reexport_map / canon
# --------------------------------------------------------------------------


class TestReexportMap:
    def test_top_level(self) -> None:
        assert mod.extract_reexport_map({"reexport_map": {"_I": "Pub"}}) == {"_I": "Pub"}

    def test_per_entry_reexported_as(self) -> None:
        prov = {"entries": [{"export_name": "_I", "reexported_as": "Pub"}]}
        assert mod.extract_reexport_map(prov) == {"_I": "Pub"}

    def test_top_level_wins(self) -> None:
        prov = {
            "reexport_map": {"_I": "FromTop"},
            "entries": [{"export_name": "_I", "reexported_as": "FromEntry"}],
        }
        assert mod.extract_reexport_map(prov) == {"_I": "FromTop"}

    def test_canon_maps_internal_to_public(self) -> None:
        assert mod.canon("_I", {"_I": "Pub"}) == "Pub"

    def test_canon_idempotent_on_public(self) -> None:
        assert mod.canon("Pub", {"_I": "Pub"}) == "Pub"


# --------------------------------------------------------------------------
# check_citation
# --------------------------------------------------------------------------


class TestCheckCitation:
    def test_valid(self, tmp_path: Path) -> None:
        _write_source(tmp_path, "src/a.ts", 10)
        assert mod.check_citation("src/a.ts", 5, tmp_path) is None

    def test_line_out_of_bounds(self, tmp_path: Path) -> None:
        _write_source(tmp_path, "src/a.ts", 10)
        assert mod.check_citation("src/a.ts", 999, tmp_path) == mod.STALE_LINE_OOB

    def test_line_zero_out_of_bounds(self, tmp_path: Path) -> None:
        _write_source(tmp_path, "src/a.ts", 10)
        assert mod.check_citation("src/a.ts", 0, tmp_path) == mod.STALE_LINE_OOB

    def test_file_missing(self, tmp_path: Path) -> None:
        assert mod.check_citation("src/gone.ts", 1, tmp_path) == mod.STALE_FILE_MISSING

    def test_null_line_tolerated(self, tmp_path: Path) -> None:
        _write_source(tmp_path, "src/a.ts", 10)
        assert mod.check_citation("src/a.ts", None, tmp_path) is None

    def test_null_file_tolerated(self, tmp_path: Path) -> None:
        assert mod.check_citation(None, 5, tmp_path) is None

    def test_line_as_numeric_string(self, tmp_path: Path) -> None:
        _write_source(tmp_path, "src/a.ts", 10)
        assert mod.check_citation("src/a.ts", "5", tmp_path) is None
        assert mod.check_citation("src/a.ts", "999", tmp_path) == mod.STALE_LINE_OOB

    def test_line_invalid_string(self, tmp_path: Path) -> None:
        _write_source(tmp_path, "src/a.ts", 10)
        assert mod.check_citation("src/a.ts", "abc", tmp_path) == mod.STALE_LINE_INVALID

    def test_backslash_path_normalized(self, tmp_path: Path) -> None:
        _write_source(tmp_path, "src/win.ts", 4)
        assert mod.check_citation("src\\win.ts", 2, tmp_path) is None


# --------------------------------------------------------------------------
# resolve_source_root
# --------------------------------------------------------------------------


class TestResolveSourceRoot:
    def test_override_wins(self, tmp_path: Path) -> None:
        override = tmp_path / "override"
        override.mkdir()
        prov = {"source_root": str(tmp_path / "other")}
        assert mod.resolve_source_root(prov, str(override)) == override

    def test_provenance_fallback(self, tmp_path: Path) -> None:
        prov = {"source_root": str(tmp_path)}
        assert mod.resolve_source_root(prov, None) == tmp_path

    def test_none_when_absent(self) -> None:
        assert mod.resolve_source_root({}, None) is None

    def test_none_when_not_a_dir(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope"
        assert mod.resolve_source_root({"source_root": str(missing)}, None) is None


# --------------------------------------------------------------------------
# verify — single-skill fixture (the core scenario)
# --------------------------------------------------------------------------


class TestVerifySingleSkill:
    def _fixture(self, tmp_path: Path) -> dict:
        src = tmp_path / "source"
        _write_source(
            src, "src/a.ts", 10,
            {3: "export const D = 1;", 5: "export function A() {}"},
        )
        metadata = {"exports": ["A", "B", "C", "E"]}
        prov = {
            "source_root": str(src),
            "entries": [
                {"export_name": "A", "source_file": "src/a.ts", "source_line": 5},
                {"export_name": "B", "source_file": "src/a.ts", "source_line": 999},
                {"export_name": "D", "source_file": "src/a.ts", "source_line": 3},
                {"export_name": "E", "source_file": "src/a.ts", "source_line": None},
            ],
        }
        return mod.verify(metadata, prov, src)

    def test_missing_is_c(self, tmp_path: Path) -> None:
        assert self._fixture(tmp_path)["missing"] == ["C"]

    def test_orphaned_is_d(self, tmp_path: Path) -> None:
        assert self._fixture(tmp_path)["orphaned"] == ["D"]

    def test_stale_b_line_out_of_bounds(self, tmp_path: Path) -> None:
        stale = self._fixture(tmp_path)["stale"]
        assert len(stale) == 1
        assert stale[0]["export_name"] == "B"
        assert stale[0]["reason"] == mod.STALE_LINE_OOB
        assert stale[0]["source_line"] == 999

    def test_null_citation_e_tolerated(self, tmp_path: Path) -> None:
        # E is neither missing (it has an entry) nor stale (null citation).
        result = self._fixture(tmp_path)
        assert "E" not in result["missing"]
        assert not any(s["export_name"] == "E" for s in result["stale"])

    def test_summary_counts(self, tmp_path: Path) -> None:
        summary = self._fixture(tmp_path)["summary"]
        assert summary["exports_checked"] == 4
        assert summary["entries_checked"] == 4
        assert summary["missing_count"] == 1
        assert summary["orphaned_count"] == 1
        assert summary["stale_count"] == 1
        # A, B, D have resolvable citations; E's null line is not counted.
        assert summary["citations_checked"] == 3
        assert summary["stale_check"] == "checked"

    def test_status_findings(self, tmp_path: Path) -> None:
        assert self._fixture(tmp_path)["status"] == "findings"


# --------------------------------------------------------------------------
# verify — stack skill: reexport canonicalization + file-missing
# --------------------------------------------------------------------------


class TestVerifyStackSkill:
    def _fixture(self, tmp_path: Path) -> dict:
        src = tmp_path / "multi"
        _write_source(src, "lib/foo.ts", 5, {2: "export class _FooImpl {}"})
        metadata = {"exports": ["Foo", "Bar"]}
        prov = {
            "source_root": str(src),
            "reexport_map": {"_FooImpl": "Foo"},
            "entries": [
                # internal name; canonicalizes to public "Foo"
                {"export_name": "_FooImpl", "source_file": "lib/foo.ts", "source_line": 2},
                # citation points at a file that does not exist → stale
                {"export_name": "Bar", "source_file": "lib/missing.ts", "source_line": 1},
            ],
        }
        return mod.verify(metadata, prov, src)

    def test_canonicalization_no_missing(self, tmp_path: Path) -> None:
        # _FooImpl canonicalizes to Foo, so Foo is not "missing".
        assert self._fixture(tmp_path)["missing"] == []

    def test_canonicalization_no_orphan(self, tmp_path: Path) -> None:
        # The internal-named entry is not an orphan after canonicalization.
        assert self._fixture(tmp_path)["orphaned"] == []

    def test_file_missing_stale(self, tmp_path: Path) -> None:
        stale = self._fixture(tmp_path)["stale"]
        assert len(stale) == 1
        assert stale[0]["export_name"] == "Bar"
        assert stale[0]["reason"] == mod.STALE_FILE_MISSING


# --------------------------------------------------------------------------
# verify — stale check skipped when no source root
# --------------------------------------------------------------------------


class TestVerifyNoSourceRoot:
    def test_stale_skipped(self) -> None:
        metadata = {"exports": ["A"]}
        prov = {
            "entries": [
                {"export_name": "A", "source_file": "src/a.ts", "source_line": 999},
            ]
        }
        result = mod.verify(metadata, prov, None)
        assert result["stale"] == []
        assert result["summary"]["stale_check"] == "skipped-no-source-root"
        assert result["summary"]["citations_checked"] == 0
        # completeness + orphan diffs still run
        assert result["missing"] == []
        assert result["orphaned"] == []
        assert result["status"] == "pass"


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestCli:
    def test_clean_exit_0(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_source(src, "a.ts", 10, {3: "export function A() {}"})
        meta = _write_json(tmp_path / "metadata.json", {"exports": ["A"]})
        prov = _write_json(
            tmp_path / "provenance-map.json",
            {
                "source_root": str(src),
                "entries": [
                    {"export_name": "A", "source_file": "a.ts", "source_line": 3}
                ],
            },
        )
        result = _run_cli(
            "verify", "--metadata", str(meta), "--provenance", str(prov)
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "pass"
        assert payload["summary"]["stale_check"] == "checked"

    def test_findings_exit_1(self, tmp_path: Path) -> None:
        meta = _write_json(tmp_path / "metadata.json", {"exports": ["A", "B"]})
        prov = _write_json(
            tmp_path / "provenance-map.json",
            {"entries": [{"export_name": "A"}]},
        )
        result = _run_cli(
            "verify", "--metadata", str(meta), "--provenance", str(prov)
        )
        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "findings"
        assert payload["missing"] == ["B"]

    def test_output_flag_writes_file(self, tmp_path: Path) -> None:
        meta = _write_json(tmp_path / "metadata.json", {"exports": ["A"]})
        prov = _write_json(
            tmp_path / "provenance-map.json",
            {"entries": [{"export_name": "A"}]},
        )
        out = tmp_path / "out.json"
        result = _run_cli(
            "verify",
            "--metadata",
            str(meta),
            "--provenance",
            str(prov),
            "-o",
            str(out),
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["status"] == "pass"

    def test_source_root_override(self, tmp_path: Path) -> None:
        src = tmp_path / "actual-src"
        _write_source(src, "a.ts", 4)
        meta = _write_json(tmp_path / "metadata.json", {"exports": ["A"]})
        prov = _write_json(
            tmp_path / "provenance-map.json",
            {
                "source_root": str(tmp_path / "nonexistent"),
                "entries": [
                    {"export_name": "A", "source_file": "a.ts", "source_line": 99}
                ],
            },
        )
        result = _run_cli(
            "verify",
            "--metadata",
            str(meta),
            "--provenance",
            str(prov),
            "--source-root",
            str(src),
        )
        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["summary"]["stale_check"] == "checked"
        assert payload["stale"][0]["reason"] == mod.STALE_LINE_OOB

    def test_missing_metadata_exit_2(self, tmp_path: Path) -> None:
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": []})
        result = _run_cli(
            "verify",
            "--metadata",
            str(tmp_path / "nope.json"),
            "--provenance",
            str(prov),
        )
        assert result.returncode == 2
        assert "not found" in result.stderr

    def test_malformed_provenance_exit_2(self, tmp_path: Path) -> None:
        meta = _write_json(tmp_path / "metadata.json", {"exports": []})
        bad = tmp_path / "provenance-map.json"
        bad.write_text("{nope", encoding="utf-8")
        result = _run_cli(
            "verify", "--metadata", str(meta), "--provenance", str(bad)
        )
        assert result.returncode == 2
        assert "malformed JSON" in result.stderr


# --------------------------------------------------------------------------
# Definition lines: Python (#530 AC 2)
# --------------------------------------------------------------------------

# A blank line above an `async def`, and a three-line decorator above a def.
PY_API = """\
from typing import Any
from pkg.impl import helper as run_helper

LIMIT: int = 10
DEFAULT = 3

async def search(query: str) -> list:
    return []

@deprecated(
    reason="use remove",
)
async def delete(item_id: int) -> None:
    return None


class Client:
    def update(self) -> None:
        pass
"""
# Line numbers in PY_API.
PY_SEARCH_DEF = 7
PY_DECORATOR = (10, 11, 12)
PY_DELETE_DEF = 13


def _py_verify(tmp_path: Path, entries: list[dict]) -> dict:
    src = tmp_path / "src"
    _write_text(src, "pkg/api.py", PY_API)
    metadata = {"exports": sorted({e["export_name"] for e in entries})}
    return mod.verify(metadata, {"entries": entries}, src)


def _stale_for(result: dict, name: str) -> list[dict]:
    return [s for s in result["stale"] if s["export_name"] == name]


class TestDefinitionLinesPython:
    def test_line_one_early_blank(self, tmp_path: Path) -> None:
        result = _py_verify(tmp_path, [
            {"export_name": "search", "source_file": "pkg/api.py",
             "source_line": PY_SEARCH_DEF - 1},
        ])
        (item,) = _stale_for(result, "search")
        assert item["reason"] == mod.STALE_LINE_NOT_DEFINITION
        assert item["definition_lines"] == [PY_SEARCH_DEF]
        assert item["source_line"] == PY_SEARCH_DEF - 1
        assert result["status"] == "findings"

    def test_line_inside_decorator(self, tmp_path: Path) -> None:
        for line in PY_DECORATOR:
            result = _py_verify(tmp_path, [
                {"export_name": "delete", "source_file": "pkg/api.py",
                 "source_line": line},
            ])
            (item,) = _stale_for(result, "delete")
            assert item["reason"] == mod.STALE_LINE_NOT_DEFINITION
            assert item["definition_lines"] == [PY_DELETE_DEF]

    def test_exact_lines_and_import_alias_pass(self, tmp_path: Path) -> None:
        result = _py_verify(tmp_path, [
            {"export_name": "search", "source_file": "pkg/api.py", "source_line": 7},
            {"export_name": "delete", "source_file": "pkg/api.py", "source_line": 13},
            {"export_name": "run_helper", "source_file": "pkg/api.py", "source_line": 2},
            {"export_name": "Any", "source_file": "pkg/api.py", "source_line": 1},
            {"export_name": "Client", "source_file": "pkg/api.py", "source_line": 17},
            {"export_name": "LIMIT", "source_file": "pkg/api.py", "source_line": 4},
            {"export_name": "DEFAULT", "source_file": "pkg/api.py", "source_line": 5},
        ])
        assert result["stale"] == []
        assert result["status"] == "pass"
        assert result["summary"]["line_check_skipped"] == 0

    def test_import_original_name_is_not_bound(self, tmp_path: Path) -> None:
        # `from pkg.impl import helper as run_helper` binds run_helper, not helper.
        result = _py_verify(tmp_path, [
            {"export_name": "helper", "source_file": "pkg/api.py", "source_line": 2},
        ])
        (item,) = _stale_for(result, "helper")
        assert item["definition_lines"] == []

    def test_dotted_name_uses_last_segment_indented(self, tmp_path: Path) -> None:
        result = _py_verify(tmp_path, [
            {"export_name": "Client.update", "source_file": "pkg/api.py",
             "source_line": 18},
        ])
        assert result["stale"] == []

    def test_dotted_name_line_off_by_one(self, tmp_path: Path) -> None:
        result = _py_verify(tmp_path, [
            {"export_name": "Client.update", "source_file": "pkg/api.py",
             "source_line": 19},
        ])
        (item,) = _stale_for(result, "Client.update")
        assert item["definition_lines"] == [18]

    def test_name_gone(self, tmp_path: Path) -> None:
        result = _py_verify(tmp_path, [
            {"export_name": "vanished", "source_file": "pkg/api.py", "source_line": 7},
        ])
        (item,) = _stale_for(result, "vanished")
        assert item["reason"] == mod.STALE_LINE_NOT_DEFINITION
        assert item["definition_lines"] == []

    def test_every_defining_line_listed(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "m.py", "def f():\n    pass\n\n\ndef f():\n    pass\n")
        result = mod.verify(
            {"exports": ["f"]},
            {"entries": [{"export_name": "f", "source_file": "m.py", "source_line": 2}]},
            src,
        )
        assert result["stale"][0]["definition_lines"] == [1, 5]

    def test_rules_unit(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "rules.py", "\n".join([
            "import os",                                  # 1  binds os
            "import numpy as np",                         # 2  binds np
            "import a.b.c",                               # 3  binds a
            "from x import (",                            # 4
            "    first,",                                 # 5  binds first
            "    second as renamed,  # trailing comment", # 6  binds renamed
            ")",                                          # 7
            "from y import (third, fourth)",              # 8  binds third, fourth
            "value = 1",                                  # 9  binds value (col 0)
            "    value = 2",                              # 10 indented: not for a plain name
            "if value == 1:",                             # 11 comparison, not assignment
            "typed: dict[str, int] = {}",                 # 12 binds typed
            "value += 3",                                 # 13 augmented, not a definition
            "class Thing:",                               # 14
            "    async def run(self):",                   # 15
            "        pass",                               # 16
            "def valueless():",                           # 17 other name
        ]) + "\n")

        def lines(name: str) -> list[int] | None:
            return mod.find_definition_lines("rules.py", name, src)

        assert lines("os") == [1]
        assert lines("np") == [2]
        assert lines("numpy") == []
        assert lines("a") == [3]
        assert lines("first") == [5]
        assert lines("renamed") == [6]
        assert lines("second") == []
        assert lines("third") == [8] and lines("fourth") == [8]
        assert lines("value") == [9]
        assert lines("Thing.value") == [9, 10]
        assert lines("typed") == [12]
        assert lines("Thing") == [14]
        assert lines("run") == [15]

    def test_pyi_extension(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "stub.pyi", "\ndef f() -> int: ...\n")
        assert mod.find_definition_lines("stub.pyi", "f", src) == [2]


# --------------------------------------------------------------------------
# Definition lines: TS/JS
# --------------------------------------------------------------------------


TS_API = """\
export async function fetchAll(): Promise<void> {}
export default class Store {}
export interface Options { a: number }
export type Id = string;
export const enum Mode { A }
export declare const VERSION: string;
export abstract class Base {}
let counter = 0;
var legacy = 1;
function* walk() {}
export function *gen() {}
enum Color { Red }
export { counter as count, legacy };
export {
  walk,
  gen as generate,
} from "./walk";
export type { Options as Opts } from "./opts";
const notCounter = 2;
"""


class TestDefinitionLinesTsJs:
    def _lines(self, tmp_path: Path, name: str, rel: str = "src/api.ts") -> list[int] | None:
        src = tmp_path / "src-root"
        _write_text(src, rel, TS_API)
        return mod.find_definition_lines(rel, name, src)

    def test_declarations(self, tmp_path: Path) -> None:
        expect = {
            "fetchAll": [1], "Store": [2], "Options": [3], "Id": [4],
            "Mode": [5], "VERSION": [6], "Base": [7], "walk": [10, 15],
            "gen": [11], "Color": [12], "notCounter": [19],
        }
        for name, lines in expect.items():
            assert self._lines(tmp_path, name) == lines, name

    def test_export_lists_use_exposed_name(self, tmp_path: Path) -> None:
        assert self._lines(tmp_path, "count") == [13]
        assert self._lines(tmp_path, "counter") == [8]  # `counter as count` exposes count
        assert self._lines(tmp_path, "legacy") == [9, 13]
        assert self._lines(tmp_path, "generate") == [16]
        assert self._lines(tmp_path, "Opts") == [18]

    def test_other_extensions(self, tmp_path: Path) -> None:
        for rel in ("a.tsx", "a.mts", "a.cts", "a.js", "a.jsx", "a.mjs", "a.cjs"):
            assert self._lines(tmp_path, "Store", rel) == [2], rel

    def test_verify_flags_line_off_by_one(self, tmp_path: Path) -> None:
        src = tmp_path / "src-root"
        _write_text(src, "src/api.ts", TS_API)
        result = mod.verify(
            {"exports": ["Store"]},
            {"entries": [{"export_name": "Store", "source_file": "src/api.ts",
                          "source_line": 3}]},
            src,
        )
        (item,) = result["stale"]
        assert item["reason"] == mod.STALE_LINE_NOT_DEFINITION
        assert item["definition_lines"] == [2]


# --------------------------------------------------------------------------
# Line check: skipped entries and the older reasons
# --------------------------------------------------------------------------


class TestLineCheckScope:
    def test_module_package_and_other_languages_skipped(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "pkg/__init__.py", "import os\n")
        _write_text(src, "lib.rs", "pub fn nothing_here() {}\n")
        entries = [
            {"export_name": "pkg", "export_type": "module",
             "source_file": "pkg/__init__.py", "source_line": 1},
            {"export_name": "pkg.sub", "export_type": "package",
             "source_file": "pkg/__init__.py", "source_line": 1},
            {"export_name": "run", "export_type": "function",
             "source_file": "lib.rs", "source_line": 1},
        ]
        result = mod.verify(
            {"exports": ["pkg", "pkg.sub", "run"]}, {"entries": entries}, src
        )
        assert result["stale"] == []
        assert result["status"] == "pass"
        assert result["summary"]["line_check_skipped"] == 3
        assert result["summary"]["citations_checked"] == 3

    def test_existing_reasons_win(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "a.py", "def a():\n    pass\n")
        entries = [
            {"export_name": "gone", "source_file": "missing.py", "source_line": 1},
            {"export_name": "a", "source_file": "a.py", "source_line": 99},
        ]
        result = mod.verify({"exports": ["gone", "a"]}, {"entries": entries}, src)
        reasons = {s["export_name"]: s for s in result["stale"]}
        assert reasons["gone"]["reason"] == mod.STALE_FILE_MISSING
        assert reasons["a"]["reason"] == mod.STALE_LINE_OOB
        assert all("definition_lines" not in s for s in result["stale"])
        assert result["summary"]["line_check_skipped"] == 0

    def test_null_line_not_checked(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "a.py", "x = 1\n")
        result = mod.verify(
            {"exports": ["a"]},
            {"entries": [{"export_name": "a", "source_file": "a.py", "source_line": None}]},
            src,
        )
        assert result["stale"] == []
        assert result["summary"]["line_check_skipped"] == 0

    def test_no_source_root_skips_line_check(self) -> None:
        result = mod.verify(
            {"exports": ["a"]},
            {"entries": [{"export_name": "a", "source_file": "a.py", "source_line": 2}]},
            None,
        )
        assert result["stale"] == []
        assert result["summary"]["line_check_skipped"] == 0


# --------------------------------------------------------------------------
# Citation prefixes (--skill-dir, #530 AC 3)
# --------------------------------------------------------------------------


def _skill(tmp_path: Path, skill_md: str, refs: dict[str, str] | None = None) -> Path:
    skill = tmp_path / "skill"
    _write_text(skill, "SKILL.md", skill_md)
    for rel, text in (refs or {}).items():
        _write_text(skill / "references", rel, text)
    return skill


READ_ENTRY = {"export_name": "search", "source_file": "pkg/api.py",
              "source_line": 7, "extraction_method": "source-read"}
AST_ENTRY = {"export_name": "delete", "source_file": "pkg/api.py",
             "source_line": 13, "extraction_method": "ast-grep"}


class TestCitationPrefixes:
    def test_prefix_mismatch_on_source_read_entry(self, tmp_path: Path) -> None:
        skill = _skill(tmp_path, "# S\n\nUse `search` [AST:pkg/api.py:L7].\n")
        result = mod.verify(
            {"exports": ["search", "delete"]},
            {"entries": [READ_ENTRY, AST_ENTRY]}, None, skill,
        )
        (item,) = result["citations"]
        assert item == {
            "file": "SKILL.md", "line": 3,
            "citation": "[AST:pkg/api.py:L7]", "prefix": "AST",
            "cited_file": "pkg/api.py", "cited_line": 7,
            "reason": mod.CITATION_PREFIX_MISMATCH,
            "expected_prefix": "SRC", "export_name": "search",
        }
        assert result["status"] == "findings"
        assert result["summary"]["citation_check"] == "checked"

    def test_src_citation_on_ast_grep_entry(self, tmp_path: Path) -> None:
        skill = _skill(tmp_path, "[SRC:pkg/api.py:L13]\n")
        result = mod.verify(
            {"exports": ["delete"]}, {"entries": [AST_ENTRY]}, None, skill
        )
        (item,) = result["citations"]
        assert item["reason"] == mod.CITATION_PREFIX_MISMATCH
        assert item["expected_prefix"] == "AST"
        assert item["export_name"] == "delete"

    def test_ast_without_ast_grep(self, tmp_path: Path) -> None:
        skill = _skill(
            tmp_path,
            "[AST:pkg/other.py:L3] and [AST:pkg/api.py:L7]\n",
            {"api.md": "[AST:pkg/api.py:L9-12]\n"},
        )
        result = mod.verify(
            {"exports": ["search"]}, {"entries": [READ_ENTRY]}, None, skill
        )
        by_citation = {(c["file"], c["citation"]): c for c in result["citations"]}
        assert len(by_citation) == 3
        unmatched = by_citation[("SKILL.md", "[AST:pkg/other.py:L3]")]
        assert unmatched["reason"] == mod.CITATION_AST_WITHOUT_AST_GREP
        assert unmatched["expected_prefix"] == "SRC"
        assert unmatched["export_name"] is None
        # One finding per citation, and prefix-mismatch wins.
        matched = by_citation[("SKILL.md", "[AST:pkg/api.py:L7]")]
        assert matched["reason"] == mod.CITATION_PREFIX_MISMATCH
        ranged = by_citation[("references/api.md", "[AST:pkg/api.py:L9-12]")]
        assert ranged["reason"] == mod.CITATION_AST_WITHOUT_AST_GREP
        assert ranged["cited_line"] == 9

    def test_matching_prefixes_pass(self, tmp_path: Path) -> None:
        skill = _skill(
            tmp_path,
            "[SRC:pkg/api.py:L7] [AST:./pkg/api.py:L13-L20]\n",
            {"deep/nested.md": "[SRC:pkg\\api.py:L7]\n"},
        )
        result = mod.verify(
            {"exports": ["search", "delete"]},
            {"entries": [READ_ENTRY, AST_ENTRY]}, None, skill,
        )
        assert result["citations"] == []
        assert result["status"] == "pass"
        assert result["summary"]["skill_citations_scanned"] == 3

    def test_unmatched_and_lineless_citations_ignored(self, tmp_path: Path) -> None:
        skill = _skill(
            tmp_path,
            "[SRC:pkg/other.py:L1] [AST:pkg/api.py] [AST:pkg/unknown.py:L4]\n",
        )
        result = mod.verify(
            {"exports": ["delete"]}, {"entries": [AST_ENTRY]}, None, skill
        )
        # The map has an ast-grep entry, so an unmatched [AST:] is no finding.
        assert result["citations"] == []
        assert result["summary"]["skill_citations_scanned"] == 2

    def test_shared_line_agrees_with_one_entry(self, tmp_path: Path) -> None:
        other = dict(READ_ENTRY, export_name="search_alias",
                     extraction_method="ast-grep")
        skill = _skill(tmp_path, "[AST:pkg/api.py:L7]\n")
        result = mod.verify(
            {"exports": ["search", "search_alias"]},
            {"entries": [READ_ENTRY, other]}, None, skill,
        )
        assert result["citations"] == []

    def test_no_skill_dir(self, tmp_path: Path) -> None:
        result = mod.verify({"exports": ["search"]}, {"entries": [READ_ENTRY]}, None)
        assert result["citations"] == []
        assert result["summary"]["citation_check"] == "skipped-no-skill-dir"
        assert result["summary"]["skill_citations_scanned"] == 0
        assert result["status"] == "pass"

    def test_sorted_by_file_line_column(self, tmp_path: Path) -> None:
        skill = _skill(
            tmp_path,
            "x\n[AST:b.py:L2] [AST:a.py:L1]\n",
            {"z.md": "[AST:c.py:L1]\n", "a.md": "[AST:d.py:L1]\n"},
        )
        result = mod.verify({"exports": []}, {"entries": []}, None, skill)
        order = [(c["file"], c["line"], c["citation"]) for c in result["citations"]]
        assert order == [
            ("SKILL.md", 2, "[AST:b.py:L2]"),
            ("SKILL.md", 2, "[AST:a.py:L1]"),
            ("references/a.md", 1, "[AST:d.py:L1]"),
            ("references/z.md", 1, "[AST:c.py:L1]"),
        ]


# --------------------------------------------------------------------------
# CLI: the new checks
# --------------------------------------------------------------------------


class TestCliNewChecks:
    def _files(self, tmp_path: Path, line: int) -> tuple[Path, Path, Path]:
        src = tmp_path / "src"
        _write_text(src, "pkg/api.py", PY_API)
        meta = _write_json(tmp_path / "metadata.json", {"exports": ["search"]})
        prov = _write_json(
            tmp_path / "provenance-map.json",
            {"entries": [dict(READ_ENTRY, source_line=line)]},
        )
        return src, meta, prov

    def test_line_not_definition_exit_1(self, tmp_path: Path) -> None:
        src, meta, prov = self._files(tmp_path, PY_SEARCH_DEF - 1)
        result = _run_cli(
            "verify", "--metadata", str(meta), "--provenance", str(prov),
            "--source-root", str(src),
        )
        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stale"][0]["definition_lines"] == [PY_SEARCH_DEF]
        assert payload["summary"]["citation_check"] == "skipped-no-skill-dir"

    def test_exact_line_exit_0(self, tmp_path: Path) -> None:
        src, meta, prov = self._files(tmp_path, PY_SEARCH_DEF)
        result = _run_cli(
            "verify", "--metadata", str(meta), "--provenance", str(prov),
            "--source-root", str(src),
        )
        assert result.returncode == 0, result.stdout

    def test_skill_dir_prefix_mismatch_exit_1(self, tmp_path: Path) -> None:
        src, meta, prov = self._files(tmp_path, PY_SEARCH_DEF)
        skill = _skill(tmp_path, "[AST:pkg/api.py:L7]\n")
        result = _run_cli(
            "verify", "--metadata", str(meta), "--provenance", str(prov),
            "--source-root", str(src), "--skill-dir", str(skill),
        )
        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stale"] == []
        assert payload["citations"][0]["reason"] == mod.CITATION_PREFIX_MISMATCH
        assert payload["summary"]["citation_check"] == "checked"

    def test_missing_skill_dir_exit_2(self, tmp_path: Path) -> None:
        _, meta, prov = self._files(tmp_path, PY_SEARCH_DEF)
        result = _run_cli(
            "verify", "--metadata", str(meta), "--provenance", str(prov),
            "--skill-dir", str(tmp_path / "nope"),
        )
        assert result.returncode == 2
        assert "skill dir not found" in result.stderr


# --------------------------------------------------------------------------
# Review pass 1: shapes the rules now cover (matrix row "Covered shapes")
# --------------------------------------------------------------------------


TS_STORE = """\
export class Store {
  private state = 0;
  static readonly VERSION = "1";

  update(next: number): void {
    this.state = next;
    update(next);
  }

  get size(): number {
    return 1;
  }

  static create(): Store {
    return new Store();
  }
}
export namespace Utils {
  export function helper() {}
}
export import Alias = Utils.helper;
export * as ns from "./ns";
export default Store;
function local() {
  const handlers = {
    update: 1,
  };
}
"""

CJS_API = """\
exports.bar = function bar() {};
module.exports.baz = 2;
module.exports = {
  qux,
  quux: 1,
  corge(a) {
    return { grault: 1 };
  },
  "garply": 2,
};
"""

PY_SHAPES = '''\
"""Module docstring.

search = not a definition
"""
try:
    FAST = True
except ImportError:
    FAST = False
x: int
first, second = 1, 2
left = right = 3
type Alias = int
type Pair[T] = tuple[T, T]
from pkg import \\
    alpha, \\
    beta as gamma


def build(
    query: str,
    top_k: int = 10,
):
    return call(
        search=query,
    )
'''


def _verify_one(tmp_path: Path, rel: str, text: str, name: str, line: int,
                **entry: object) -> dict:
    src = tmp_path / "src"
    _write_text(src, rel, text)
    return mod.verify(
        {"exports": [name]},
        {"entries": [dict({"export_name": name, "source_file": rel,
                           "source_line": line}, **entry)]},
        src,
    )


class TestCoveredShapes:
    def test_ts_class_members_for_dotted_names(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "store.ts", TS_STORE)

        def lines(name: str) -> list[int] | None:
            return mod.find_definition_lines("store.ts", name, src)

        assert lines("Store.update") == [5]  # line 7 `update(next);` is a call
        assert lines("Store.state") == [2]
        assert lines("Store.VERSION") == [3]
        assert lines("Store.size") == [10]
        assert lines("Store.create") == [14]
        # an undotted name never matches a class member
        assert lines("update") == []

    def test_ts_member_exit_0_at_its_line(self, tmp_path: Path) -> None:
        result = _verify_one(tmp_path, "store.ts", TS_STORE, "Store.update", 5)
        assert result["status"] == "pass"
        result = _verify_one(tmp_path, "store.ts", TS_STORE, "Store.update", 4)
        assert result["stale"][0]["definition_lines"] == [5]

    def test_ts_export_forms(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "store.ts", TS_STORE)

        def lines(name: str) -> list[int] | None:
            return mod.find_definition_lines("store.ts", name, src)

        assert lines("Utils") == [18]          # namespace
        assert lines("Utils.helper") == [19]
        assert lines("Alias") == [21]          # export import NAME =
        assert lines("ns") == [22]             # export * as NAME from
        assert lines("Store") == [1, 23]       # class and export default NAME

    def test_commonjs(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "api.cjs", CJS_API)

        def lines(name: str) -> list[int] | None:
            return mod.find_definition_lines("api.cjs", name, src)

        assert lines("bar") == [1]
        assert lines("baz") == [2]
        assert lines("qux") == [4]      # shorthand
        assert lines("quux") == [5]     # key
        assert lines("corge") == [6]    # method shorthand
        assert lines("garply") == [9]   # quoted key
        assert lines("grault") == []    # nested object key is not an export
        assert _verify_one(tmp_path, "api.cjs", CJS_API, "bar", 1)["status"] == "pass"

    def test_python_shapes(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "shapes.py", PY_SHAPES)

        def lines(name: str) -> list[int] | None:
            return mod.find_definition_lines("shapes.py", name, src)

        assert lines("FAST") == [6, 8]      # under try: / except:
        assert lines("x") == [9]            # annotation only
        assert lines("first") == [10] and lines("second") == [10]
        assert lines("left") == [11] and lines("right") == [11]
        assert lines("Alias") == [12]       # PEP 695
        assert lines("Pair") == [13]
        assert lines("alpha") == [15]       # backslash-continued import
        assert lines("gamma") == [16]
        assert lines("beta") == []
        # a docstring line, parameters and a keyword argument never match
        assert lines("search") == []
        assert lines("query") == []
        assert lines("top_k") == []

    def test_try_block_and_annotation_exit_0(self, tmp_path: Path) -> None:
        assert _verify_one(tmp_path, "shapes.py", PY_SHAPES, "FAST", 6)["status"] == "pass"
        assert _verify_one(tmp_path, "shapes.py", PY_SHAPES, "x", 9)["status"] == "pass"

    def test_bom_hides_no_line_1(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        (src).mkdir(parents=True)
        (src / "bom.ts").write_bytes(b"\xef\xbb\xbfexport function first() {}\n")
        (src / "bom.py").write_bytes(b"\xef\xbb\xbfdef first():\n    pass\n")
        assert mod.find_definition_lines("bom.ts", "first", src) == [1]
        assert mod.find_definition_lines("bom.py", "first", src) == [1]
        result = mod.verify(
            {"exports": ["first"]},
            {"entries": [{"export_name": "first", "source_file": "bom.ts",
                          "source_line": 1}]},
            src,
        )
        assert result["status"] == "pass"

    def test_crlf_lines_number_like_the_citation_check(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "crlf.py").write_bytes(b"import os\r\n\r\ndef run():\r\n    pass\r\n")
        (src / "crlf.ts").write_bytes(b"// head\r\nexport const run = 1;\r\n")
        assert mod.find_definition_lines("crlf.py", "run", src) == [3]
        assert mod.find_definition_lines("crlf.ts", "run", src) == [2]
        assert mod.check_citation("crlf.py", 4, src) is None
        assert mod.check_citation("crlf.py", 5, src) == mod.STALE_LINE_OOB

    def test_untokenizable_python_is_matched_line_by_line(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "broken.py", 'def run():\n    x = """never closed\n')
        assert mod.find_definition_lines("broken.py", "run", src) == [1]


class TestLocalShadow:
    PY = "config = load()\n\n\ndef build():\n    config = {}\n    return config\n"
    TS = "export const config = {};\nfunction build() {\n  const config = 1;\n}\n"

    def test_python_column_0_wins(self, tmp_path: Path) -> None:
        result = _verify_one(tmp_path, "m.py", self.PY, "config", 1)
        assert result["status"] == "pass"
        result = _verify_one(tmp_path, "m.py", self.PY, "config", 2)
        assert result["stale"][0]["definition_lines"] == [1]

    def test_ts_column_0_wins(self, tmp_path: Path) -> None:
        result = _verify_one(tmp_path, "m.ts", self.TS, "config", 1)
        assert result["status"] == "pass"
        result = _verify_one(tmp_path, "m.ts", self.TS, "config", 2)
        assert result["stale"][0]["definition_lines"] == [1]

    def test_recorded_indented_match_is_kept(self, tmp_path: Path) -> None:
        # The recorded line is the local shadow the column-0 rule dropped:
        # the finding keeps it, so it lists two lines and is never auto-moved.
        result = _verify_one(tmp_path, "m.py", self.PY, "config", 5)
        (item,) = result["stale"]
        assert item["reason"] == mod.STALE_LINE_NOT_DEFINITION
        assert item["definition_lines"] == [1, 5]
        result = _verify_one(tmp_path, "m.ts", self.TS, "config", 3)
        assert result["stale"][0]["definition_lines"] == [1, 3]
        # find_definition_lines itself still applies the column-0 rule.
        assert mod.find_definition_lines("m.ts", "config", tmp_path / "src") == [1]

    def test_undotted_method_beside_module_function(self, tmp_path: Path) -> None:
        text = "def update():\n    pass\n\n\nclass Store:\n    def update(self):\n        pass\n"
        result = _verify_one(tmp_path, "m.py", text, "update", 6)
        assert result["stale"][0]["definition_lines"] == [1, 6]

    def test_indented_only_matches_count(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "m.py", "def build():\n    config = {}\n")
        assert mod.find_definition_lines("m.py", "config", src) == [2]

    def test_dotted_name_keeps_every_match(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "m.py", self.PY)
        assert mod.find_definition_lines("m.py", "Builder.config", src) == [1, 5]

    def test_multiline_import_line_takes_its_statement_column(self, tmp_path: Path) -> None:
        # `run,` sits indented inside a column-0 import, so it counts as
        # module level and the indented local `def run` is dropped.
        src = tmp_path / "src"
        _write_text(src, "m.py", "from x import (\n    run,\n)\n\n\ndef f():\n    def run():\n        pass\n")
        assert mod.find_definition_lines("m.py", "run", src) == [2]


# --------------------------------------------------------------------------
# Review pass 1: helper hygiene
# --------------------------------------------------------------------------


class TestHelperHygiene:
    def test_export_type_case_insensitive(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "pkg/__init__.py", "import os\n")
        result = mod.verify(
            {"exports": ["pkg"]},
            {"entries": [{"export_name": "pkg", "export_type": "Module",
                          "source_file": "pkg/__init__.py", "source_line": 1}]},
            src,
        )
        assert result["status"] == "pass"
        assert result["summary"]["line_check_skipped"] == 1

    def test_blank_source_file_tolerated_not_counted(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        result = mod.verify(
            {"exports": ["a"]},
            {"entries": [{"export_name": "a", "source_file": "  ", "source_line": 3}]},
            src,
        )
        assert result["stale"] == []
        assert result["summary"]["line_check_skipped"] == 0
        assert result["summary"]["citations_checked"] == 0

    def test_barrel_internal_name_uses_raw_name(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "lib/foo.ts", "// head\nexport class _FooImpl {}\n\n")
        prov = {
            "reexport_map": {"_FooImpl": "Foo"},
            "entries": [{"export_name": "_FooImpl", "source_file": "lib/foo.ts",
                         "source_line": 3}],
        }
        result = mod.verify({"exports": ["Foo"]}, prov, src)
        (item,) = result["stale"]
        assert item["export_name"] == "_FooImpl"
        assert item["reason"] == mod.STALE_LINE_NOT_DEFINITION
        assert item["definition_lines"] == [2]
        assert result["missing"] == [] and result["orphaned"] == []
        prov["entries"][0]["source_line"] = 2
        assert mod.verify({"exports": ["Foo"]}, prov, src)["status"] == "pass"

    def test_no_rule_match_is_an_empty_list(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "m.ts", "export default function () {}\n")
        result = mod.verify(
            {"exports": ["handler"]},
            {"entries": [{"export_name": "handler", "source_file": "m.ts",
                          "source_line": 1}]},
            src,
        )
        (item,) = result["stale"]
        assert item["reason"] == mod.STALE_LINE_NOT_DEFINITION
        assert item["definition_lines"] == []
        assert result["status"] == "findings"


class TestCitationHygiene:
    def test_ast_bridge_and_source_reading(self, tmp_path: Path) -> None:
        bridge = {"export_name": "a", "source_file": "m.py", "source_line": 1,
                  "extraction_method": "ast_bridge"}
        reading = {"export_name": "b", "source_file": "m.py", "source_line": 2,
                   "extraction_method": "source_reading"}
        skill = _skill(tmp_path, "[AST:m.py:L1] [SRC:m.py:L2]\n[SRC:m.py:L1] [AST:m.py:L2]\n")
        result = mod.verify({"exports": ["a", "b"]}, {"entries": [bridge, reading]},
                            None, skill)
        got = [(c["line"], c["citation"], c["reason"], c["expected_prefix"])
               for c in result["citations"]]
        assert got == [
            (2, "[SRC:m.py:L1]", mod.CITATION_PREFIX_MISMATCH, "AST"),
            (2, "[AST:m.py:L2]", mod.CITATION_PREFIX_MISMATCH, "SRC"),
        ]

    def test_non_string_method_is_unknown(self, tmp_path: Path) -> None:
        odd = {"export_name": "a", "source_file": "m.py", "source_line": 1,
               "extraction_method": ["ast-grep"]}
        obj = {"export_name": "b", "source_file": "m.py", "source_line": 2,
               "extraction_method": {"tool": "ast-grep"}}
        skill = _skill(tmp_path, "[SRC:m.py:L1] [AST:m.py:L2]\n")
        result = mod.verify({"exports": ["a", "b"]}, {"entries": [odd, obj]},
                            None, skill)
        # No crash. Both methods are unknown, so nothing proves the map has
        # no ast-grep entry: the [AST:] citation is not flagged.
        assert result["citations"] == []
        assert result["summary"]["skill_citations_matched"] == 2

    def test_skill_citations_matched(self, tmp_path: Path) -> None:
        skill = _skill(tmp_path, "[SRC:pkg/api.py:L7] [SRC:other/root/api.py:L7]\n")
        result = mod.verify({"exports": ["search"]}, {"entries": [READ_ENTRY]},
                            None, skill)
        assert result["summary"]["skill_citations_scanned"] == 2
        assert result["summary"]["skill_citations_matched"] == 1
        skill2 = _skill(tmp_path / "b", "[SRC:elsewhere/api.py:L7]\n")
        result = mod.verify({"exports": ["search"]}, {"entries": [READ_ENTRY]},
                            None, skill2)
        assert result["summary"]["skill_citations_scanned"] == 1
        assert result["summary"]["skill_citations_matched"] == 0
        no_dir = mod.verify({"exports": ["search"]}, {"entries": [READ_ENTRY]}, None)
        assert no_dir["summary"]["skill_citations_matched"] == 0

    def test_bom_markdown(self, tmp_path: Path) -> None:
        skill = tmp_path / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_bytes("﻿[AST:pkg/api.py:L7]\n".encode("utf-8"))
        result = mod.verify({"exports": ["search"]}, {"entries": [READ_ENTRY]},
                            None, skill)
        (item,) = result["citations"]
        assert item["line"] == 1 and item["reason"] == mod.CITATION_PREFIX_MISMATCH

    def test_skill_dir_without_skill_md_exit_2(self, tmp_path: Path) -> None:
        meta = _write_json(tmp_path / "metadata.json", {"exports": []})
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": []})
        empty = tmp_path / "empty-skill"
        (empty / "references").mkdir(parents=True)
        result = _run_cli(
            "verify", "--metadata", str(meta), "--provenance", str(prov),
            "--skill-dir", str(empty),
        )
        assert result.returncode == 2
        assert result.stdout == ""
        assert "no SKILL.md" in result.stderr


# --------------------------------------------------------------------------
# Review pass 2: comments and strings, heuristics, star imports, CLI errors
# --------------------------------------------------------------------------


def _ts_lines(tmp_path: Path, rel: str, text: str, name: str) -> list[int] | None:
    src = tmp_path / "src"
    _write_text(src, rel, text)
    return mod.find_definition_lines(rel, name, src)


class TestTsMemberHeuristics:
    def test_wrapped_parameter_list(self, tmp_path: Path) -> None:
        text = "export class Store {\n  update(\n    next: number,\n  ): void {}\n}\n"
        assert _ts_lines(tmp_path, "s.ts", text, "Store.update") == [2]

    def test_parameter_types_with_brackets(self, tmp_path: Path) -> None:
        text = ("export class Store {\n"
                "  update(cb: () => void, opts: { a: number }): void {}\n"
                "}\n")
        assert _ts_lines(tmp_path, "s.ts", text, "Store.update") == [2]

    def test_arrow_tail_is_not_a_member(self, tmp_path: Path) -> None:
        text = ("export class Store {\n"
                "  run() {\n"
                "    return this.items.map(\n"
                "      update => apply(update)\n"
                "    );\n"
                "  }\n"
                "}\n")
        assert _ts_lines(tmp_path, "s.ts", text, "Store.update") == []

    def test_jsdoc_line_is_not_a_member(self, tmp_path: Path) -> None:
        text = ("export class Store {\n"
                "  /**\n"
                "   * update\n"
                "   * @param next the value\n"
                "   */\n"
                "  update(next: number): void {}\n"
                "}\n")
        assert _ts_lines(tmp_path, "s.ts", text, "Store.update") == [6]


class TestJsCommentsAndStrings:
    def test_block_commented_export(self, tmp_path: Path) -> None:
        text = ("/*\n"
                "export const foo = 1;\n"
                "*/\n"
                "export const foo = 2;\n"
                "/* export const bar = 1; */ export const baz = 2;\n"
                "// export const qux = 1;\n")
        assert _ts_lines(tmp_path, "c.ts", text, "foo") == [4]
        assert _ts_lines(tmp_path, "c.ts", text, "bar") == []
        assert _ts_lines(tmp_path, "c.ts", text, "baz") == [5]
        assert _ts_lines(tmp_path, "c.ts", text, "qux") == []

    def test_comment_markers_inside_strings(self, tmp_path: Path) -> None:
        text = ('const glob = "src/**/*.ts";\n'
                "export const after = 1;\n"
                "const re = /\\/*/;\n"
                "export const later = 2;\n")
        assert _ts_lines(tmp_path, "c.ts", text, "after") == [2]
        assert _ts_lines(tmp_path, "c.ts", text, "later") == [4]

    def test_url_string_in_module_exports_object(self, tmp_path: Path) -> None:
        text = ("module.exports = {\n"
                '  url: "http://example.com/a",\n'
                '  brace: "{(",\n'
                "  a,\n"
                "};\n"
                "exports.b = 2;\n")
        assert _ts_lines(tmp_path, "u.js", text, "url") == [2]
        assert _ts_lines(tmp_path, "u.js", text, "a") == [4]
        assert _ts_lines(tmp_path, "u.js", text, "b") == [6]

    def test_one_line_module_exports_object(self, tmp_path: Path) -> None:
        text = ('module.exports = { qux, quux: 1, url: "http://x" };\n'
                "exports.b = 2;\n")
        assert _ts_lines(tmp_path, "o.js", text, "qux") == [1]
        assert _ts_lines(tmp_path, "o.js", text, "quux") == [1]
        assert _ts_lines(tmp_path, "o.js", text, "b") == [2]


class TestStarImportFallback:
    def test_star_import_counts_when_nothing_else_does(self, tmp_path: Path) -> None:
        text = "from .impl import *  # re-export\nfrom .other import helper\n"
        result = _verify_one(tmp_path, "pkg/__init__.py", text, "search", 1)
        assert result["status"] == "pass"
        src = tmp_path / "src"
        assert mod.find_definition_lines("pkg/__init__.py", "search", src) == [1]

    def test_star_import_ignored_when_the_file_defines_the_name(self, tmp_path: Path) -> None:
        text = "from .impl import *\n\n\ndef search():\n    pass\n"
        result = _verify_one(tmp_path, "pkg/__init__.py", text, "search", 1)
        assert result["stale"][0]["definition_lines"] == [4]


class TestAstWithoutAstGrepNeedsKnownMethods:
    def test_missing_method_blocks_the_reason(self, tmp_path: Path) -> None:
        no_method = {"export_name": "a", "source_file": "m.py", "source_line": 1}
        skill = _skill(tmp_path, "[AST:m.py:L1] [AST:other.py:L9]\n")
        result = mod.verify({"exports": ["a"]}, {"entries": [no_method, READ_ENTRY]},
                            None, skill)
        assert result["citations"] == []

    def test_unknown_method_blocks_the_reason(self, tmp_path: Path) -> None:
        odd = dict(READ_ENTRY, export_name="b", source_line=9,
                   extraction_method="direct-read")
        skill = _skill(tmp_path, "[AST:pkg/other.py:L3]\n")
        result = mod.verify({"exports": ["search", "b"]},
                            {"entries": [READ_ENTRY, odd]}, None, skill)
        assert result["citations"] == []

    def test_all_known_and_none_ast(self, tmp_path: Path) -> None:
        qmd = dict(READ_ENTRY, export_name="b", source_line=9,
                   extraction_method="qmd_bridge")
        # An entry with no source line does not need a known method.
        loose = {"export_name": "c", "extraction_method": "direct-read"}
        skill = _skill(tmp_path, "[AST:pkg/other.py:L3]\n")
        result = mod.verify({"exports": ["search", "b", "c"]},
                            {"entries": [READ_ENTRY, qmd, loose]}, None, skill)
        (item,) = result["citations"]
        assert item["reason"] == mod.CITATION_AST_WITHOUT_AST_GREP

    def test_non_dict_entries_are_skipped(self, tmp_path: Path) -> None:
        skill = _skill(tmp_path, "[AST:pkg/api.py:L7]\n")
        result = mod.verify({"exports": ["search"]},
                            {"entries": ["junk", None, 3, ["x"], READ_ENTRY]},
                            None, skill)
        (item,) = result["citations"]
        assert item["reason"] == mod.CITATION_PREFIX_MISMATCH
        assert item["export_name"] == "search"


class TestCliErrors:
    def _inputs(self, tmp_path: Path) -> tuple[Path, Path]:
        meta = _write_json(tmp_path / "metadata.json", {"exports": []})
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": []})
        return meta, prov

    def test_unexpected_error_exits_2(self, tmp_path: Path, monkeypatch, capsys) -> None:
        meta, prov = self._inputs(tmp_path)

        def boom(*_args: object, **_kwargs: object) -> dict:
            raise PermissionError("denied:\nreferences/api.md")

        monkeypatch.setattr(mod, "verify", boom)
        code = mod.main(["verify", "--metadata", str(meta), "--provenance", str(prov)])
        out, err = capsys.readouterr()
        assert code == 2
        assert out == ""
        assert err.strip() == (
            "error: verification failed: PermissionError: denied: references/api.md"
        )

    def test_file_as_skill_dir(self, tmp_path: Path) -> None:
        meta, prov = self._inputs(tmp_path)
        not_dir = _write_text(tmp_path, "SKILL.md", "# S\n")
        result = _run_cli(
            "verify", "--metadata", str(meta), "--provenance", str(prov),
            "--skill-dir", str(not_dir),
        )
        assert result.returncode == 2
        assert "skill dir is not a directory" in result.stderr
        assert "not found" not in result.stderr
