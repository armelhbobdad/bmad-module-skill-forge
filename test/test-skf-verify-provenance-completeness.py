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
    a `--skill-dir` with no SKILL.md) and on an `-o` file that cannot be
    written, for each subcommand
  - node kinds with `--check-node-kinds` (#530 BH4), ast-grep mocked: one
    test per I/O matrix row (invalid kind, valid kinds, `ERROR`, entries
    not checked, flag absent, no ast-grep, one call per (language, kind)),
    `ERROR` and kinds not shaped like a kind judged without ast-grep, no
    lookup when nothing is left to ask, the call shape (`--config` naming
    the temporary folder's minimal sgconfig.yml), the calibration kind, the
    first timeout ending the calls, a temporary-folder error, failures
    listed in `node_kinds_unchecked[]`, entry index and line on each item,
    the extension map, the CWD-shim guard and its pinned copy; with the
    ast-grep version package.json pins on PATH, its verdicts on real and
    invented kinds in every mapped language and a CLI run under a broken
    ancestor sgconfig.yml
  - definition shapes the recipes cite (#560): later declarators, on one
    line and over several as Prettier writes them (after a comma, inside a
    bracket, after `=`, before a line starting `?`, `:` or `.`, after a
    split keyword and a multi-line arrow), quoted export names, a name on
    the line after its keyword (and the Python `def \\` form), decorators;
    the negatives (a name in a string, a comment, a regular expression, a
    generic's type parameters or JSX on a declarator line, a destructuring
    default, a decorator argument, a line after the statement ended) and
    the column-0 rule for a split name and a later declarator
  - reference apps (#549): no missing / orphaned set-diff and
    `summary.set_diff: not-applicable`; `entry_index` on each stale item
  - definition-lines: each `line_check`, `line_is_definition`, the dropped
    indented line, the default source root
  - classify-stale (test-skill's fabricated-signature test): every entry
    file-missing, one entry defining the name, no entry, a checked file
    without the name, an unchecked export type, a file-less entry alone
    and in either place beside a missing file, the first cited entry's
    citation, a repeated name, a bare name list, and exit 2 on bad input
  - classify-stale's `defined_at` (#678): column-0 declarations that count
    (Python and TS/JS, an `as` alias that renames included) and the
    imports, re-exports, same-name aliases, import-valued bindings
    (`require(...)`, `(await) import(...)`, on the line or the next),
    locals, comments and untokenizable files that do not; a cited file
    first, else exactly one declaring file of the walk (a homonym gives
    null); the walk root, the entries' shared folder widened to its
    package root (`__init__.py` chain, nearest `package.json`), leaving
    out an entry outside every package, else the source root; the skipped
    places (installed and built output, test configuration, `*.min.js`),
    judged below the walk root, and `lib/` walked; the rule families the
    map cites; no lookup for a fabricated or dotted name; a cited path
    outside the root and a symlink anywhere on a path never read; a
    lookup error gives null with exit 0; one pass, each file read once
    and no walk after cited hits; the lookup rules opt-in, the default
    `require` declarator kept; and the skip sets pinned to their sources;
    a module or package named after the name declaring it (at line 1 when
    no line of it does), and `declared_in` listing every walked
    declaration of a name the walk looked for, a stub beside its
    implementation counted once; no package root at the source root
    (a stray `__init__.py`), a walk that never leaves the source root,
    and an untokenizable file that holds the name making it ambiguous
  - declared_line (#682): the defined_at rule for one file, read below the
    source root or from lines given (a dunder, a renaming alias, a module
    or package named after the name, that module rule optional), None for
    an import, a local, a dotted name, another language, a missing file,
    a path outside the root, a symlink on the path or a skipped file, one
    read per file over one SourceCache, and the lookup's own answer
  - baseline_gaps (#687): the map entries an extraction left out that their
    file still declares (a dunder, a renaming alias, a module or package),
    a real deletion left out, and the held, re-exported, listed, dotted,
    unchecked-file and other-language entries
  - kind-at: recipes from markdown fences and each YAML file shape, the
    language forms, and with the pinned ast-grep: every language the
    recipes cover, the name filter, ambiguous, incomplete and skipped
    answers, the Prettier layout's line; mocked: no ast-grep, the rule
    passed in a file, the first timeout ending the calls, a backslash
    `--file`
  - fix (#584): a byte-for-byte fixture with the LIMIT/DEFAULT one-pass
    move, ranges, a normalized path, a shared line and a [MANUAL] block
    that must not change (manual-verify ok), a second verify and fix;
    dry run, --no-line-moves, findings left for a person, entry lookup,
    CRLF / BOM / non-UTF-8 bytes, writes through skf-atomic-write.py,
    input errors, a failed re-check or `-o` after the writes (exit 2,
    naming the files written), and the [MANUAL] markers pinned to
    skf-hash-content.py (ASCII whitespace included)
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

import pytest


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

    def test_an_unwritable_result_exits_2(self, tmp_path: Path) -> None:
        # never exit 1, which verify and kind-at give as an answer
        meta, prov = self._inputs(tmp_path)
        src = tmp_path / "src"
        _write_text(src, "a.py", "def a(): pass\n")
        gone = str(tmp_path / "gone" / "out.json")
        runs = [
            ["verify", "--metadata", str(meta), "--provenance", str(prov)],
            ["definition-lines", "--source-root", str(src), "--file", "a.py", "--name", "a"],
            ["kind-at", "--source-root", str(src), "--file", "a.py", "--line", "1",
             "--recipes", str(EXTRACTION_PATTERNS)],
        ]
        for args in runs:
            result = _run_cli(*args, "-o", gone)
            assert (result.returncode, result.stdout) == (2, ""), args
            assert result.stderr.startswith(f"error: writing {gone} failed: "), args
            assert result.stderr.count("\n") == 1, args


# --------------------------------------------------------------------------
# Node kinds (--check-node-kinds, #530 BH4): ast-grep is mocked
# --------------------------------------------------------------------------

MERGE_CCC = REPO_ROOT / "src" / "shared" / "scripts" / "skf-merge-ccc-exclusions.py"
REJECTION = (
    "Error: Cannot parse rule INLINE_RULES\n"
    "Help: The file is not a valid ast-grep rule.\n\n"
    "✖ Caused by\n"
    "╰▻ Rule contains invalid kind matcher.\n"
    "╰▻ Invalid Kind\n"
    "╰▻ Kind `{kind}` is invalid.\n"
)
REAL_KINDS = {
    "python": {"function_definition", "class_definition"},
    "typescript": {"export_statement"},
    "tsx": {"export_statement", "call_expression"},
    "javascript": {"export_statement"},
    "rust": {"function_item"},
    "go": {"function_declaration"},
    "java": {"method_declaration"},
}


def _pinned_ast_grep_version() -> str:
    """The ast-grep-cli version package.json's test:python installs."""
    scripts = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    match = re.search(r"--with ast-grep-cli==([\w.]+)", scripts["test:python"])
    assert match, "package.json test:python pins no ast-grep-cli version"
    return match.group(1)


def _pinned_ast_grep() -> str | None:
    """The ast-grep on PATH when it is the pinned version, else None."""
    exe = shutil.which("ast-grep")
    if exe is None:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    ok = out.returncode == 0 and out.stdout.split()[-1:] == [_pinned_ast_grep_version()]
    return exe if ok else None


class FakeAstGrep:
    """`subprocess.run` stand-in answering like ast-grep 0.45.3 does.

    `overrides` maps a kind to the result (or exception) every call about
    that kind gets; the calibration kind answers like the real binary unless
    it is overridden too.
    """

    def __init__(self, overrides: dict | None = None) -> None:
        self.calls: list[tuple[list[str], dict]] = []
        self.overrides = overrides or {}
        self.folder_files: list[list[str]] = []
        self.configs: list[str] = []

    def __call__(self, cmd: list[str], **kwargs: object) -> SimpleNamespace:
        self.calls.append((list(cmd), dict(kwargs)))
        cwd = kwargs.get("cwd")
        self.folder_files.append(sorted(p.name for p in Path(str(cwd)).iterdir()))
        config = Path(cmd[cmd.index("--config") + 1])
        self.configs.append(config.read_text(encoding="utf-8") if config.is_file() else "")
        rule = json.loads(cmd[cmd.index("--inline-rules") + 1])
        kind = rule["rule"]["kind"]
        if kind in self.overrides:
            answer = self.overrides[kind]
            if isinstance(answer, BaseException):
                raise answer
            return answer
        if kind in REAL_KINDS.get(rule["language"], set()):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=8, stdout="", stderr=REJECTION.format(kind=kind))

    def asked(self, calibration: bool = False) -> list[tuple[str, str]]:
        out = []
        for cmd, _ in self.calls:
            rule = json.loads(cmd[cmd.index("--inline-rules") + 1])
            pair = (rule["language"], rule["rule"]["kind"])
            if calibration or pair[1] != mod.BOGUS_NODE_KIND:
                out.append(pair)
        return out


def _which_ast_grep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/opt/bin/ast-grep" if name == "ast-grep" else None)


@pytest.fixture
def ast_grep(monkeypatch: pytest.MonkeyPatch) -> FakeAstGrep:
    fake = FakeAstGrep()
    _which_ast_grep(monkeypatch)
    monkeypatch.setattr(mod.subprocess, "run", fake)
    return fake


def _use(monkeypatch: pytest.MonkeyPatch, fake: FakeAstGrep) -> FakeAstGrep:
    _which_ast_grep(monkeypatch)
    monkeypatch.setattr(mod.subprocess, "run", fake)
    return fake


def _ast_entry(name: str, rel: str, kind: object, method: str = "ast-grep", line: object = 1) -> dict:
    return {"export_name": name, "source_file": rel, "source_line": line,
            "confidence": "T1", "extraction_method": method, "ast_node_type": kind}


def _kinds(entries: list, check: bool = True) -> dict:
    names = [e["export_name"] for e in entries
             if isinstance(e, dict) and isinstance(e.get("export_name"), str)]
    return mod.verify({"exports": names}, {"entries": entries}, None, None, check)


def _main(tmp_path: Path, entries: list[dict], capsys, *flags: str) -> tuple[int, dict]:
    names = [e["export_name"] for e in entries]
    meta = _write_json(tmp_path / "metadata.json", {"exports": names})
    prov = _write_json(tmp_path / "provenance-map.json", {"entries": entries})
    code = mod.main(["verify", "--metadata", str(meta), "--provenance", str(prov), *flags])
    return code, json.loads(capsys.readouterr().out)


class TestNodeKindMatrix:
    def test_invalid_kind(self, tmp_path: Path, ast_grep: FakeAstGrep, capsys) -> None:
        entries = [_ast_entry("add", "cognee/x.py", "async_function_definition", line=42)]
        code, out = _main(tmp_path, entries, capsys, "--check-node-kinds")
        assert code == 1
        assert out["status"] == "findings"
        assert out["node_kinds"] == [{
            "export_name": "add", "entry_index": 0, "source_file": "cognee/x.py",
            "source_line": 42, "ast_node_type": "async_function_definition",
            "language": "python", "reason": mod.NODE_KIND_INVALID,
        }]
        assert out["node_kinds_unchecked"] == []
        assert out["summary"]["node_kind_check"] == "checked"
        assert out["summary"]["node_kinds_checked"] == 1
        assert out["summary"]["node_kind_findings_count"] == 1

    def test_valid_kinds(self, tmp_path: Path, ast_grep: FakeAstGrep, capsys) -> None:
        entries = [
            _ast_entry("search", "pkg/api.py", "function_definition"),
            _ast_entry("createServer", "src/server.ts", "export_statement"),
            _ast_entry("props", "src/Button.tsx", "call_expression"),
        ]
        code, out = _main(tmp_path, entries, capsys, "--check-node-kinds")
        assert code == 0, out
        assert out["status"] == "pass"
        assert out["node_kinds"] == [] and out["node_kinds_unchecked"] == []
        assert out["summary"]["node_kinds_checked"] == 3
        assert ast_grep.asked() == [
            ("python", "function_definition"), ("tsx", "call_expression"),
            ("typescript", "export_statement")]

    def test_error_kind(self, tmp_path: Path, ast_grep: FakeAstGrep, capsys) -> None:
        entries = [_ast_entry("broken", "pkg/api.py", "ERROR")]
        code, out = _main(tmp_path, entries, capsys, "--check-node-kinds")
        assert code == 1
        (item,) = out["node_kinds"]
        assert item["reason"] == mod.NODE_KIND_ERROR
        assert item["language"] == "python"
        assert out["summary"]["node_kinds_checked"] == 1
        assert ast_grep.calls == []  # ast-grep accepts ERROR, so it is not asked

    def test_not_checked(self, tmp_path: Path, ast_grep: FakeAstGrep, capsys) -> None:
        entries = [
            _ast_entry("read", "pkg/api.py", "import_alias", method="source-read"),
            _ast_entry("nokind", "pkg/api.py", None),
            _ast_entry("blank", "pkg/api.py", "  "),
            _ast_entry("scala", "src/Main.scala", "function_definition"),
        ]
        code, out = _main(tmp_path, entries, capsys, "--check-node-kinds")
        assert code == 0, out
        assert out["node_kinds"] == []
        assert out["summary"]["node_kind_check"] == "checked"
        assert out["summary"]["node_kinds_checked"] == 0
        assert out["summary"]["node_kind_check_skipped"] == 1
        assert ast_grep.calls == []

    def test_flag_absent_leaves_output_unchanged(self, tmp_path: Path, ast_grep: FakeAstGrep, capsys) -> None:
        entries = [_ast_entry("add", "cognee/x.py", "async_function_definition")]
        code, out = _main(tmp_path, entries, capsys)
        assert code == 0
        assert list(out) == ["status", "missing", "orphaned", "stale", "citations", "summary"]
        assert [k for k in out["summary"] if "kind" in k] == ["node_kind_check"]
        assert out["summary"]["node_kind_check"] == "not-requested"
        assert ast_grep.calls == []

    def test_no_ast_grep(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        fake = FakeAstGrep()
        monkeypatch.setattr(mod.shutil, "which", lambda name: None)
        monkeypatch.setattr(mod.subprocess, "run", fake)
        entries = [_ast_entry("add", "cognee/x.py", "async_function_definition")]
        code, out = _main(tmp_path, entries, capsys, "--check-node-kinds")
        assert code == 0
        assert out["node_kinds"] == [] and out["node_kinds_unchecked"] == []
        assert out["summary"]["node_kind_check"] == "skipped-no-ast-grep"
        assert out["summary"]["node_kinds_checked"] == 0
        assert fake.calls == []

    def test_dedupe(self, ast_grep: FakeAstGrep) -> None:
        entries = [_ast_entry(f"f{i}", f"pkg/m{i % 5}.py", "function_definition") for i in range(35)]
        result = _kinds(entries)
        assert result["status"] == "pass"
        assert ast_grep.asked() == [("python", "function_definition")]
        assert result["summary"]["node_kinds_checked"] == 35


class TestNodeKindWithoutAstGrep:
    """ERROR and kinds that are not kind-shaped are judged without ast-grep."""

    def test_error_flagged_without_ast_grep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod.shutil, "which", lambda name: None)
        result = _kinds([_ast_entry("add", "x.py", "async_function_definition"),
                         _ast_entry("broken", "y.py", "ERROR")])
        assert result["summary"]["node_kind_check"] == "skipped-no-ast-grep"
        assert [(i["export_name"], i["reason"]) for i in result["node_kinds"]] == [
            ("broken", mod.NODE_KIND_ERROR)]
        assert result["status"] == "findings"

    def test_no_candidates_is_checked_without_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        looked_up: list[str] = []
        monkeypatch.setattr(mod.shutil, "which", lambda name: looked_up.append(name))
        for entries in ([], [_ast_entry("read", "x.py", "import_alias", method="source-read")],
                        [_ast_entry("broken", "x.py", "ERROR")]):
            summary = _kinds(entries)["summary"]
            assert summary["node_kind_check"] == "checked"
            assert summary["node_kind_check_errors"] == 0
        assert looked_up == []

    @pytest.mark.parametrize("kind", [
        " function_definition", "function_definition ", "function_definition\n",
        "a&b", "a|b", "%PATH%", "a^b", "a-b", "1abc", "fn()", 'we"ird', "ké",
    ])
    def test_kind_not_shaped_like_a_kind(self, ast_grep: FakeAstGrep, kind: str) -> None:
        result = _kinds([_ast_entry("q", "a/b.py", kind)])
        assert [(i["ast_node_type"], i["reason"]) for i in result["node_kinds"]] == [
            (kind, mod.NODE_KIND_INVALID)]
        assert result["summary"]["node_kinds_checked"] == 1
        assert ast_grep.calls == []


class TestNodeKindAstGrepCalls:
    def test_call_shape(self, ast_grep: FakeAstGrep) -> None:
        _kinds([_ast_entry("q", "a/b.py", "function_definition")])
        assert ast_grep.asked(calibration=True) == [
            ("python", mod.BOGUS_NODE_KIND), ("python", "function_definition")]
        for cmd, kwargs in ast_grep.calls:
            folder = kwargs["cwd"]
            assert cmd[:3] == ["/opt/bin/ast-grep", "scan", "--config"]
            assert cmd[3] == str(Path(folder) / "sgconfig.yml")
            assert cmd[4] == "--inline-rules" and cmd[6:] == ["--stdin"]
            assert kwargs["input"] == ""
            assert kwargs["timeout"] == mod.NODE_KIND_TIMEOUT_SEC
            assert kwargs["check"] is False
        assert json.loads(ast_grep.calls[1][0][5]) == {
            "id": "skf-node-kind", "language": "python", "rule": {"kind": "function_definition"}}
        assert ast_grep.folder_files == [["sgconfig.yml"], ["sgconfig.yml"]]
        assert ast_grep.configs == [mod.MINIMAL_SGCONFIG] * 2

    def test_each_language_is_asked_its_own_kinds(self, ast_grep: FakeAstGrep) -> None:
        entries = [
            _ast_entry("a", "x.py", "export_statement"),
            _ast_entry("b", "x.ts", "export_statement"),
            _ast_entry("c", "x.mjs", "export_statement"),
            _ast_entry("d", "x.rs", "function_item"),
            _ast_entry("e", "x.go", "function_declaration"),
            _ast_entry("f", "x.go", "function_item"),
            _ast_entry("g", "X.java", "method_declaration"),
        ]
        result = _kinds(entries)
        assert [(i["export_name"], i["language"]) for i in result["node_kinds"]] == [
            ("a", "python"), ("f", "go")]
        assert len(ast_grep.asked()) == 7

    def test_ast_bridge_checked_other_methods_not(self, ast_grep: FakeAstGrep) -> None:
        entries = [
            _ast_entry("bridge", "x.py", "import_alias", method="ast_bridge"),
            _ast_entry("cased", "x.py", "import_alias", method="Ast-Grep"),
            _ast_entry("stack", "x.py", "import_alias", method="source_reading"),
            dict(_ast_entry("listy", "x.py", "import_alias"), extraction_method=["ast-grep"]),
        ]
        result = _kinds(entries)
        assert [i["export_name"] for i in result["node_kinds"]] == ["bridge"]

    def test_names_indexes_and_order(self, ast_grep: FakeAstGrep) -> None:
        entries = [
            _ast_entry("num", "x.py", 7),
            {"source_file": "z.py", "extraction_method": "ast-grep", "ast_node_type": "bogus"},
            _ast_entry("b", "a.py", "bogus"),
            "not-a-dict",
            _ast_entry("a", "b.py", "bogus", line=9),
            _ast_entry("a", "b.py", "bogus", line=3),
        ]
        result = _kinds(entries)
        assert [(i["export_name"], i["source_file"], i["entry_index"], i["source_line"])
                for i in result["node_kinds"]] == [
            (None, "z.py", 1, None), ("a", "b.py", 4, 9), ("a", "b.py", 5, 3), ("b", "a.py", 2, 1)]
        assert ast_grep.asked() == [("python", "bogus")]

    def test_other_failures_are_listed_unchecked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for answer in (
            SimpleNamespace(returncode=2, stdout="", stderr="error: unexpected argument '--stdin' found\n"),
            SimpleNamespace(returncode=8, stdout="", stderr="Error: Cannot parse configuration\n"),
            FileNotFoundError("gone"),
        ):
            fake = _use(monkeypatch, FakeAstGrep({"function_definition": answer}))
            result = _kinds([_ast_entry("a", "x.py", "function_definition", line=5),
                             _ast_entry("b", "y.py", "function_definition"),
                             _ast_entry("e", "y.py", "ERROR")])
            assert [i["reason"] for i in result["node_kinds"]] == [mod.NODE_KIND_ERROR]
            assert [(i["export_name"], i["source_line"], i["reason"])
                    for i in result["node_kinds_unchecked"]] == [
                ("a", 5, mod.UNCHECKED_AST_GREP_ERROR), ("b", 1, mod.UNCHECKED_AST_GREP_ERROR)]
            assert result["summary"]["node_kind_check_errors"] == 2
            assert result["summary"]["node_kinds_checked"] == 1
            assert fake.asked() == [("python", "function_definition")]

    def test_first_timeout_stops_asking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        timeout = subprocess.TimeoutExpired(cmd="ast-grep", timeout=1)
        fake = _use(monkeypatch, FakeAstGrep({"class_definition": timeout}))
        result = _kinds([_ast_entry("a", "x.py", "class_definition"),
                         _ast_entry("b", "x.py", "function_definition"),
                         _ast_entry("c", "x.py", "zzz_bogus")])
        # pairs are asked in sorted order: class_definition first
        assert fake.asked() == [("python", "class_definition")]
        assert {i["export_name"]: i["reason"] for i in result["node_kinds_unchecked"]} == {
            "a": mod.UNCHECKED_TIMEOUT, "b": mod.UNCHECKED_TIMEOUT, "c": mod.UNCHECKED_TIMEOUT}
        assert result["node_kinds"] == []
        assert result["summary"]["node_kind_check"] == "checked"

    def test_temp_folder_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _use(monkeypatch, FakeAstGrep())

        def no_folder(*_args: object, **_kwargs: object) -> None:
            raise PermissionError("no temp folder")

        monkeypatch.setattr(mod.tempfile, "TemporaryDirectory", no_folder)
        result = _kinds([_ast_entry("a", "x.py", "import_alias"),
                         _ast_entry("e", "x.py", "ERROR")])
        assert [i["reason"] for i in result["node_kinds"]] == [mod.NODE_KIND_ERROR]
        assert [(i["export_name"], i["reason"]) for i in result["node_kinds_unchecked"]] == [
            ("a", mod.UNCHECKED_TEMP_FOLDER)]
        assert result["summary"]["node_kind_check"] == "checked"
        assert fake.calls == []

    def test_config_write_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _use(monkeypatch, FakeAstGrep())
        real_open = open

        def failing_open(path, *args, **kwargs):
            if str(path).endswith("sgconfig.yml"):
                raise OSError("read-only")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", failing_open)
        result = _kinds([_ast_entry("a", "x.py", "import_alias")])
        assert [i["reason"] for i in result["node_kinds_unchecked"]] == [mod.UNCHECKED_TEMP_FOLDER]
        assert fake.calls == []

    @pytest.mark.parametrize("answer", [
        SimpleNamespace(returncode=0, stdout="", stderr=""),
        SimpleNamespace(returncode=8, stdout="", stderr="Error: Cannot parse configuration\n"),
        subprocess.TimeoutExpired(cmd="ast-grep", timeout=1),
    ], ids=["accepts-anything", "other-error", "timeout"])
    def test_unrecognized_ast_grep_flags_nothing(self, monkeypatch: pytest.MonkeyPatch, answer) -> None:
        fake = _use(monkeypatch, FakeAstGrep({mod.BOGUS_NODE_KIND: answer}))
        result = _kinds([_ast_entry("a", "x.py", "import_alias"),
                         _ast_entry("e", "x.py", "ERROR")])
        assert result["summary"]["node_kind_check"] == "skipped-unrecognized-ast-grep"
        assert [i["reason"] for i in result["node_kinds"]] == [mod.NODE_KIND_ERROR]
        assert result["node_kinds_unchecked"] == []
        assert fake.asked(calibration=True) == [("python", mod.BOGUS_NODE_KIND)]

    def test_findings_join_other_findings(self, ast_grep: FakeAstGrep) -> None:
        result = mod.verify({"exports": ["gone"]},
                            {"entries": [_ast_entry("add", "x.py", "import_alias")]}, None, None, True)
        assert result["missing"] == ["gone"] and result["orphaned"] == ["add"]
        assert result["node_kinds"][0]["reason"] == mod.NODE_KIND_INVALID
        assert result["status"] == "findings"
        assert list(result) == ["status", "missing", "orphaned", "stale", "citations",
                                "node_kinds", "node_kinds_unchecked", "summary"]


class TestNodeKindHelpers:
    def test_extension_mapping(self) -> None:
        expected = {
            "a.py": "python", "a.pyi": "python", "a.ts": "typescript", "a.mts": "typescript",
            "a.cts": "typescript", "a.tsx": "tsx", "a.js": "javascript", "a.jsx": "javascript",
            "a.mjs": "javascript", "a.cjs": "javascript", "a.rs": "rust", "a.go": "go",
            "A.java": "java", "a.kt": "kotlin", "a.kts": "kotlin", "a.cs": "csharp",
            "a.rb": "ruby", "a.swift": "swift", "a.php": "php",
            "./src/A.PY": "python", "src\\win\\x.Tsx": "tsx",
            "a.scala": None, "a.d.ts.map": None, "Makefile": None, "": None, "  ": None,
        }
        for path, language in expected.items():
            assert mod.ast_grep_language(path) == language, path
        assert mod.ast_grep_language(None) is None
        assert mod.ast_grep_language(3) is None

    def test_cwd_shim_reads_as_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(mod.shutil, "which", lambda name: str(tmp_path / "ast-grep.cmd"))
        fake = FakeAstGrep()
        monkeypatch.setattr(mod.subprocess, "run", fake)
        result = _kinds([_ast_entry("a", "x.py", "import_alias")])
        assert result["summary"]["node_kind_check"] == "skipped-no-ast-grep"
        assert fake.calls == []

    def test_cwd_guard_code_matches_merge_helper(self) -> None:
        def body(path: Path) -> str:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            (fn,) = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name == "_resolve_outside_cwd"]
            fn = copy.deepcopy(fn)
            fn.body = fn.body[1:]  # drop the docstring
            return ast.dump(fn)

        assert body(SCRIPT_PATH) == body(MERGE_CCC)

    def test_parser_flag(self) -> None:
        args = mod._build_parser().parse_args(
            ["verify", "--metadata", "m", "--provenance", "p", "--check-node-kinds"])
        assert args.check_node_kinds is True
        args = mod._build_parser().parse_args(["verify", "--metadata", "m", "--provenance", "p"])
        assert args.check_node_kinds is False

    def test_pinned_version_is_read_from_package_json(self) -> None:
        assert re.fullmatch(r"\d+\.\d+\.\d+", _pinned_ast_grep_version())


AST_GREP = _pinned_ast_grep()


@pytest.mark.skipif(AST_GREP is None, reason="no ast-grep of the version package.json pins on PATH")
class TestNodeKindsRealAstGrep:
    """The answers the helper reads, from the pinned ast-grep on PATH."""

    def _folder(self, tmp_path: Path) -> str:
        (tmp_path / "sgconfig.yml").write_text(mod.MINIMAL_SGCONFIG, encoding="utf-8")
        return str(tmp_path)

    def test_judges_real_kinds(self, tmp_path: Path) -> None:
        folder = self._folder(tmp_path)
        judge = mod.ast_grep_judges_kind
        cases = {
            ("python", "function_definition"): "valid",
            ("python", mod.BOGUS_NODE_KIND): "invalid",
            ("python", "async_function_definition"): "invalid",
            ("python", "import_alias"): "invalid",
            ("typescript", "export_statement"): "valid",
            ("typescript", "function_definition"): "invalid",
            ("tsx", "call_expression"): "valid",
            ("go", "function_declaration"): "valid",
            ("rust", "function_item"): "valid",
            ("javascript", "export_statement"): "valid",
            ("java", "method_declaration"): "valid",
            ("kotlin", "function_declaration"): "valid",
            ("csharp", "method_declaration"): "valid",
            ("ruby", "method"): "valid",
            ("swift", "function_declaration"): "valid",
            ("php", "function_definition"): "valid",
        }
        for (language, kind), verdict in cases.items():
            assert judge(AST_GREP, language, kind, folder) == verdict, (language, kind)

    def test_every_mapped_language_rejects_the_bogus_kind(self, tmp_path: Path) -> None:
        folder = self._folder(tmp_path)
        for language in sorted(set(mod.AST_GREP_LANGUAGES.values())):
            assert mod.ast_grep_judges_kind(AST_GREP, language, mod.BOGUS_NODE_KIND, folder) == "invalid"

    def test_cli_with_broken_sgconfig_above_cwd_and_temp(self, tmp_path: Path) -> None:
        # A broken sgconfig.yml in an ancestor of both the working folder and
        # the temporary folder: without --config, every ast-grep call exits 8.
        (tmp_path / "sgconfig.yml").write_text("bogus: [\n", encoding="utf-8")
        work = tmp_path / "work"
        temp = tmp_path / "temp"
        work.mkdir()
        temp.mkdir()
        entries = [_ast_entry("add", "cognee/x.py", "async_function_definition"),
                   _ast_entry("search", "cognee/y.py", "function_definition")]
        meta = _write_json(work / "metadata.json", {"exports": ["add", "search"]})
        prov = _write_json(work / "provenance-map.json", {"entries": entries})
        env = dict(os.environ, TMPDIR=str(temp), TEMP=str(temp), TMP=str(temp))
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "verify", "--metadata", str(meta),
             "--provenance", str(prov), "--check-node-kinds"],
            capture_output=True, text=True, check=False, cwd=work, env=env,
        )
        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["summary"]["node_kind_check"] == "checked"
        assert [(i["export_name"], i["reason"]) for i in payload["node_kinds"]] == [
            ("add", mod.NODE_KIND_INVALID)]
        assert payload["node_kinds_unchecked"] == []
        assert payload["summary"]["node_kinds_checked"] == 2


# --------------------------------------------------------------------------
# Definition shapes the recipes cite (#560)
# --------------------------------------------------------------------------

# The repro in #560: each line is the one the recipes cite for its name.
SHAPES_TS = """\
export const a1 = 1, B2 = () => 2;
export { "str-name" as strAlias, four as "quoted-out" } from "./m";
export * as "strNs" from "./s";
export function
  Multi() {}
@dec export class H {}
export @sealed class Inner {}
"""
# Prettier 3.8's layout of declarator lists: a declarator with an
# initializer goes on a line of its own, and a long one breaks inside its
# brackets (type arguments included), after its `=` or before a `?`, `:`,
# `.` or `|`. The local `B2` below is dropped: a later declarator takes the
# column of its statement's line.
PRETTIER_TS = """\
export const a1 = 1,
  B2 = () => 2;
export const handler = (a: number) => {
    return a + 1;
  },
  Next = 2;
export const first = someVeryLongFunctionCall(
    argumentOne,
    argumentTwo,
    argumentThree,
  ),
  Short = 2;
export const cond = someCondition
    ? someVeryLongConsequentExpression
    : someVeryLongAlternateExpression,
  After = 3;
export const sum =
    someVeryLongOperandNumberOne + someVeryLongOperandNumberTwo + three,
  Later = 1;
export const chain = someObject
    .someVeryLongMethodName()
    .anotherVeryLongMethodName()
    .third(),
  NextOne = 2;
export const typed: Record<string, number> = { alpha: 1 },
  Typed2: Map<string, number> = new Map();
export const prevVal = previousValueFromTheStore as
    | FieldState<
        TParentDataTypeName,
        TFieldNameType,
        TFieldDataType,
        TOnMountHandlerType
      >
    | undefined,
  AfterCast = 2;
export const handlers: Record<
    SomeVeryLongKeyTypeName,
    SomeVeryLongHandlerTypeName<WithArgument>
  > = {},
  AfterRecord = 1;
function outer() {
  const B2 = 3;
}
"""


class TestDefinitionShapes:
    def test_issue_repro(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "shapes.ts", SHAPES_TS)
        _write_text(src, "split.py", "def \\\n    spaced():\n    pass\n")
        cases = [
            ("shapes.ts", 1, "B2"), ("shapes.ts", 2, "strAlias"),
            ("shapes.ts", 2, "quoted-out"), ("shapes.ts", 3, "strNs"),
            ("shapes.ts", 5, "Multi"), ("shapes.ts", 6, "H"),
            ("shapes.ts", 7, "Inner"), ("split.py", 2, "spaced"),
        ]
        for rel, line, name in cases:
            assert mod.find_definition_lines(rel, name, src) == [line], (rel, name)

    def test_later_declarators(self, tmp_path: Path) -> None:
        text = ("export const a1 = 1, B2 = () => 2;\n"
                "export let x, Y;\n"
                "export var p = f(1, 2), Q: number = 3;\n"
                "export const { de } = obj, AfterDestr = 3;\n"
                "export declare const amb: number, Other!: string;\n"
                'export const s = "a, b", T = `c, ${d}`, U = [1, 2];\n'
                "const local = 1, Hidden = 2;\n"
                "export const half = total / 2, R = total / 4;\n"
                "export const m = new Map<string, number>(), S = 1;\n"
                "export const FLAG = 1 << 3, MASK = FLAG << 1;\n")
        cases = {"a1": [1], "B2": [1], "x": [2], "Y": [2], "Q": [3],
                 "AfterDestr": [4], "Other": [5], "T": [6], "U": [6],
                 "Hidden": [7], "R": [8], "S": [9], "MASK": [10], "number": []}
        for name, lines in cases.items():
            assert _ts_lines(tmp_path, "d.ts", text, name) == lines, name

    def test_declarator_line_negatives(self, tmp_path: Path) -> None:
        # the name inside a string, a comment, a destructuring default, a
        # call's arguments, an array, a regular expression, a generic arrow
        # function's type parameters, JSX or type arguments: none of them
        # declares it
        text = ('export const a = "B, C = 1", d = 2;\n'
                "export const e = 1, /* B = 2 */ f = 3; // , C = 4\n"
                "export const { g = B } = obj;\n"
                "export const h = call(x, B = 2), i = [C, 1];\n"
                "export const j = `${B}, C = 1`, k = 1;\n"
                "export const l = 1; const m = 2, C = 3;\n"
                "export const n = <T, U = string>(a: T) => a;\n"
                "export const re = /[/,]x, B = 1/g, o = 2;\n"
                "export const el = <A>x, B = 2</A>;\n"
                "export let q = this.get<A, B, C>(hash), p = 1;\n"
                "export const s: Handler<A, U, C> = h, t = 2;\n")
        for name in ("B", "C", "U"):
            assert _ts_lines(tmp_path, "n.ts", text, name) == [], name
        cases = {"d": [1], "f": [2], "i": [4], "k": [5], "n": [7], "o": [8],
                 "el": [9], "p": [10], "t": [11]}
        for name, lines in cases.items():
            assert _ts_lines(tmp_path, "n.ts", text, name) == lines, name

    def test_prettier_declarator_lists(self, tmp_path: Path) -> None:
        # the recipes cite each later declarator's own line
        cases = {"a1": [1], "B2": [2], "handler": [3], "Next": [6], "first": [7],
                 "Short": [12], "cond": [13], "After": [16], "sum": [17],
                 "Later": [19], "chain": [20], "NextOne": [24], "typed": [25],
                 "Typed2": [26], "prevVal": [27], "AfterCast": [35],
                 "handlers": [36], "AfterRecord": [40]}
        for name, lines in cases.items():
            assert _ts_lines(tmp_path, "p.ts", PRETTIER_TS, name) == lines, name
        # what finishes a declarator declares nothing, a type argument
        # alone on its line included
        for name in ("argumentOne", "someCondition", "someVeryLongConsequentExpression",
                     "three", "someObject", "alpha", "number", "TParentDataTypeName",
                     "TFieldNameType", "SomeVeryLongKeyTypeName", "WithArgument"):
            assert _ts_lines(tmp_path, "p.ts", PRETTIER_TS, name) == [], name
        assert _verify_one(tmp_path, "p.ts", PRETTIER_TS, "B2", 2)["stale"] == []

    def test_split_keyword_list_over_several_lines(self, tmp_path: Path) -> None:
        text = ("export const\n"   # 1
                "  e = 1,\n"       # 2
                "  F = 2;\n"       # 3
                "export\n"         # 4
                "let\n"            # 5
                "  g,\n"           # 6
                "  H;\n"           # 7
                "export var\n"     # 8
                "  i =\n"          # 9
                "    j,\n"         # 10
                "  K = 3;\n")      # 11
        cases = {"e": [2], "F": [3], "g": [6], "H": [7], "i": [9], "j": [], "K": [11]}
        for name, lines in cases.items():
            assert _ts_lines(tmp_path, "s.ts", text, name) == lines, name

    def test_later_declarator_after_a_multi_line_arrow(self, tmp_path: Path) -> None:
        # every line of the initializer still goes through the other rules:
        # a local, a list nested in it (at its own column), a method
        text = ("export const handler = async (request: Request) => {\n"  # 1
                "    const inner = 1,\n"                                   # 2
                "      nested = 2;\n"                                      # 3
                "    return [inner, nested].map((n) => n * 2);\n"          # 4
                "  },\n"                                                   # 5
                "  Next = 2;\n"                                            # 6
                "export const api = {\n"                                   # 7
                "    get(url: string) {\n"                                 # 8
                "      return url;\n"                                      # 9
                "    },\n"                                                 # 10
                "  },\n"                                                   # 11
                "  Other = 1;\n")                                          # 12
        cases = {"handler": [1], "inner": [2], "nested": [3], "Next": [6], "api": [7],
                 "api.get": [8], "Other": [12], "request": [], "n": [], "url": []}
        for name, lines in cases.items():
            assert _ts_lines(tmp_path, "a.ts", text, name) == lines, name

    def test_a_list_ends_where_its_statement_does(self, tmp_path: Path) -> None:
        text = ("export const a = 1\n"   # 1  no `;`, and the next line starts
                "foo(x), B = 2\n"        # 2  a statement of its own
                "export const c = 1;\n"  # 3
                "  D = 2,\n"             # 4
                "  E = 3;\n"             # 5
                "export const f = x\n"   # 6  a comma put first goes on
                "  , G = 3;\n"           # 7
                "export const q = `\n"   # 8  a template literal over several
                "  H = 1,\n"             # 9  lines is not followed
                "`;\n")                  # 10
        cases = {"B": [], "D": [], "E": [], "G": [7], "H": []}
        for name, lines in cases.items():
            assert _ts_lines(tmp_path, "e.ts", text, name) == lines, name

    def test_const_enum_is_not_a_declarator_list(self, tmp_path: Path) -> None:
        text = "export const enum Dir { Up, Down }\n"
        assert _ts_lines(tmp_path, "e.ts", text, "Dir") == [1]
        assert _ts_lines(tmp_path, "e.ts", text, "Down") == []

    def test_quoted_export_names(self, tmp_path: Path) -> None:
        text = ("export {\n"
                "  one,\n"
                '  "str-name" as strAlias,\n'
                '  four as "quoted-out",\n'
                "  'single' as 'also-quoted',\n"
                '  "bare-string",\n'
                '} from "./multi";\n'
                "export * as \"strNs\" from './s';\n"
                "export * as 'sq' from \"./t\";\n"
                'export { x as "a,b", y };\n')
        cases = {"one": [2], "strAlias": [3], "quoted-out": [4],
                 "also-quoted": [5], "bare-string": [6], "strNs": [8],
                 "sq": [9], "a,b": [10], "y": [10]}
        for name, lines in cases.items():
            assert _ts_lines(tmp_path, "q.ts", text, name) == lines, name
        # the name before `as` is not exposed
        for name in ("str-name", "four", "single", "x"):
            assert _ts_lines(tmp_path, "q.ts", text, name) == [], name

    def test_name_on_the_line_after_its_keyword(self, tmp_path: Path) -> None:
        text = ("export function\n"        # 1
                "  Multi<P>(p: P) {}\n"    # 2
                "export interface\n"       # 3
                "  MultiLineProps\n"       # 4
                "  extends A {}\n"         # 5
                "export\n"                 # 6
                "const\n"                  # 7
                "  Spread =\n"             # 8
                "  1;\n"                   # 9
                "export default class\n"   # 10
                "  Deferred {}\n"          # 11
                "export async function*\n"  # 12
                "  gen() {}\n"             # 13
                "export const\n"           # 14
                "  first = 1, Second = 2;\n"  # 15
                "export type\n"            # 16
                "export const Z = 1;\n")   # 17
        cases = {"Multi": [2], "MultiLineProps": [4], "Spread": [8],
                 "Deferred": [11], "gen": [13], "first": [15],
                 "Second": [15], "Z": [17]}
        for name, lines in cases.items():
            assert _ts_lines(tmp_path, "s.ts", text, name) == lines, name

    def test_split_name_negatives(self, tmp_path: Path) -> None:
        # `default` is not a declaration keyword, and the name must be on
        # the very next line
        text = ("export default\n"
                "  C\n"
                "export function\n"
                "\n"
                "  Late() {}\n")
        assert _ts_lines(tmp_path, "n.ts", text, "C") == []
        assert _ts_lines(tmp_path, "n.ts", text, "Late") == []

    def test_split_name_takes_the_keyword_line_column(self, tmp_path: Path) -> None:
        # the name line is indented, but its statement starts at column 0,
        # so a local of the same name is still dropped
        text = ("function outer() {\n"
                "  const Multi = 1;\n"
                "}\n"
                "export function\n"
                "  Multi() {}\n")
        assert _ts_lines(tmp_path, "c.ts", text, "Multi") == [5]

    def test_decorators(self, tmp_path: Path) -> None:
        text = ("@dec export class H {}\n"
                "export @sealed class Inner {}\n"
                "@a.b() @c export default class D {}\n"
                "export @x.y({ z: 1 }) abstract class E {}\n"
                "@Inject(Foo) export class Bar {}\n"
                "@a.b(Baz, { k: Qux(1) }) export class Quux {}\n")
        cases = {"H": [1], "Inner": [2], "D": [3], "E": [4], "Bar": [5],
                 "Quux": [6]}
        for name, lines in cases.items():
            assert _ts_lines(tmp_path, "d.ts", text, name) == lines, name
        # a decorator's argument is not declared
        for name in ("Foo", "Baz", "Qux", "dec", "sealed"):
            assert _ts_lines(tmp_path, "d.ts", text, name) == [], name

    def test_python_split_def_and_class(self, tmp_path: Path) -> None:
        text = ("def \\\n"                  # 1
                "    spaced (a,\n"          # 2
                "            b): pass\n"    # 3
                "class \\\n"                # 4
                "  Split:\n"                # 5
                "    pass\n"                # 6
                "async def \\\n"            # 7
                "    later(): pass\n"       # 8
                '"""\n'                     # 9
                "def \\\n"                  # 10
                "    in_doc(): pass\n"      # 11
                '"""\n')                    # 12
        src = tmp_path / "src"
        _write_text(src, "s.py", text)
        cases = {"spaced": [2], "Split": [5], "later": [8], "in_doc": []}
        for name, lines in cases.items():
            assert mod.find_definition_lines("s.py", name, src) == lines, name

    def test_split_def_recorded_at_the_keyword_line(self, tmp_path: Path) -> None:
        result = _verify_one(tmp_path, "s.py", "def \\\n    spaced(): pass\n", "spaced", 1)
        (item,) = result["stale"]
        assert item["reason"] == mod.STALE_LINE_NOT_DEFINITION
        assert item["definition_lines"] == [2]


# --------------------------------------------------------------------------
# Reference apps: no exports-vs-entries set-diff (#549)
# --------------------------------------------------------------------------


class TestReferenceAppSetDiff:
    def _fixture(self, tmp_path: Path, metadata: dict, layout_line: int = 3) -> dict:
        src = tmp_path / "src"
        _write_text(src, "app.ts", "export function render() {}\n\nexport const Layout = 1;\n")
        prov = {"entries": [
            {"export_name": "render", "source_file": "app.ts", "source_line": 1},
            {"export_name": "Layout", "source_file": "app.ts", "source_line": layout_line},
        ]}
        return mod.verify(metadata, prov, src)

    def test_reference_app_skips_missing_and_orphaned(self, tmp_path: Path) -> None:
        result = self._fixture(tmp_path, {"scope_type": "reference-app", "exports": []})
        assert result["missing"] == [] and result["orphaned"] == []
        assert result["status"] == "pass"
        summary = result["summary"]
        assert summary["set_diff"] == "not-applicable"
        assert summary["missing_count"] == 0 and summary["orphaned_count"] == 0
        assert summary["entries_checked"] == 2

    def test_reference_app_still_reports_stale_lines(self, tmp_path: Path) -> None:
        result = self._fixture(
            tmp_path, {"scope_type": "reference-app", "exports": ["Other"]}, layout_line=9)
        assert result["missing"] == [] and result["orphaned"] == []
        assert [(s["export_name"], s["reason"]) for s in result["stale"]] == [
            ("Layout", mod.STALE_LINE_OOB)]
        assert result["status"] == "findings"

    def test_other_scope_types_keep_the_set_diff(self, tmp_path: Path) -> None:
        for metadata in ({"scope_type": "full-library", "exports": []}, {"exports": []},
                         {"scope_type": ["reference-app"], "exports": []}):
            result = self._fixture(tmp_path, metadata)
            assert result["orphaned"] == ["Layout", "render"]
            assert result["summary"]["set_diff"] == "checked"
            assert result["status"] == "findings"

    def test_cli_reads_scope_type_from_metadata(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "app.ts", "export function render() {}\n")
        meta = _write_json(tmp_path / "metadata.json",
                           {"scope_type": "reference-app", "exports": []})
        prov = _write_json(tmp_path / "provenance-map.json", {
            "source_root": str(src),
            "entries": [{"export_name": "render", "source_file": "app.ts", "source_line": 1}],
        })
        result = _run_cli("verify", "--metadata", str(meta), "--provenance", str(prov))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["summary"]["set_diff"] == "not-applicable"
        assert payload["orphaned"] == []


class TestStaleEntryIndex:
    def test_each_stale_item_names_its_entry(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "a.ts", "// head\nexport const A = 1;\n")
        prov = {"entries": [
            "not an entry",
            {"export_name": "A", "source_file": "a.ts", "source_line": 1},
            {"export_name": "B", "source_file": "gone.ts", "source_line": 1},
        ]}
        result = mod.verify({"exports": ["A", "B"]}, prov, src)
        assert [(s["export_name"], s["entry_index"]) for s in result["stale"]] == [
            ("A", 1), ("B", 2)]


# --------------------------------------------------------------------------
# definition-lines
# --------------------------------------------------------------------------

PY_CONFIG = '''\
"""Config."""

import os


# the limit
LIMIT = 10
DEFAULT = 3


def search(query):
    return []
'''


def _main_json(capsys, *argv: str) -> tuple[int, dict]:
    code = mod.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


class TestDefinitionLinesCommand:
    def _src(self, tmp_path: Path) -> Path:
        src = tmp_path / "src"
        _write_text(src, "lib/config.py", PY_CONFIG)
        return src

    def test_recorded_line_one_early(self, tmp_path: Path, capsys) -> None:
        src = self._src(tmp_path)
        code, out = _main_json(capsys, "definition-lines", "--source-root", str(src),
                               "--file", "lib/config.py", "--name", "LIMIT", "--line", "6")
        assert code == 0
        assert out == {"source_file": "lib/config.py", "export_name": "LIMIT",
                       "line_check": "checked", "definition_lines": [7],
                       "source_line": 6, "line_is_definition": False}

    def test_recorded_line_is_the_definition(self, tmp_path: Path, capsys) -> None:
        src = self._src(tmp_path)
        _, out = _main_json(capsys, "definition-lines", "--source-root", str(src),
                            "--file", "lib/config.py", "--name", "search", "--line", "11")
        assert out["definition_lines"] == [11] and out["line_is_definition"] is True

    def test_without_a_line(self, tmp_path: Path, capsys) -> None:
        src = self._src(tmp_path)
        _, out = _main_json(capsys, "definition-lines", "--source-root", str(src),
                            "--file", "lib/config.py", "--name", "DEFAULT")
        assert out["definition_lines"] == [8]
        assert out["source_line"] is None and out["line_is_definition"] is None

    def test_no_definition_line_is_an_empty_list(self, tmp_path: Path, capsys) -> None:
        src = self._src(tmp_path)
        _, out = _main_json(capsys, "definition-lines", "--source-root", str(src),
                            "--file", "lib/config.py", "--name", "nothing", "--line", "3")
        assert out["line_check"] == "checked"
        assert out["definition_lines"] == [] and out["line_is_definition"] is False

    def test_skips(self, tmp_path: Path, capsys) -> None:
        src = self._src(tmp_path)
        _write_text(src, "lib.rs", "pub fn add() {}\n")
        cases = [
            (["--file", "gone.py", "--name", "x"], "file-missing"),
            (["--file", "lib/config.py", "--name", "config", "--export-type", "Module"],
             "skipped-export-type"),
            (["--file", "lib.rs", "--name", "add", "--line", "1"], "skipped-language"),
        ]
        for args, status in cases:
            code, out = _main_json(capsys, "definition-lines", "--source-root", str(src), *args)
            assert code == 0
            assert out["line_check"] == status, args
            assert out["definition_lines"] is None and out["line_is_definition"] is None

    def test_a_dropped_indented_line_joins_the_answer(self, tmp_path: Path, capsys) -> None:
        # as in verify: a method recorded under an undotted name beside a
        # module-level function gives several lines, so nobody moves it
        src = tmp_path / "src"
        _write_text(src, "m.py", "def update():\n    pass\n\nclass App:\n    def update(self):\n        pass\n")
        _, out = _main_json(capsys, "definition-lines", "--source-root", str(src),
                            "--file", "m.py", "--name", "update", "--line", "5")
        assert out["definition_lines"] == [1, 5] and out["line_is_definition"] is False
        result = _verify_one(tmp_path, "m.py", (src / "m.py").read_text(encoding="utf-8"),
                             "update", 5)
        assert result["stale"][0]["definition_lines"] == out["definition_lines"]

    def test_source_root_defaults_to_the_current_folder(
        self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = self._src(tmp_path)
        monkeypatch.chdir(src)
        _, out = _main_json(capsys, "definition-lines", "--file", "lib/config.py",
                            "--name", "LIMIT")
        assert out["definition_lines"] == [7]

    def test_missing_source_root_exit_2(self, tmp_path: Path) -> None:
        result = _run_cli("definition-lines", "--source-root", str(tmp_path / "nope"),
                          "--file", "a.py", "--name", "x")
        assert result.returncode == 2
        assert result.stdout == "" and "source root not found" in result.stderr


# --------------------------------------------------------------------------
# classify-stale
# --------------------------------------------------------------------------


class TestClassifyStale:
    def _run(self, tmp_path: Path, capsys, stale: list[str], entries: list[dict]) -> tuple[int, list[dict]]:
        """classify-stale over reconcile-coverage.py's result, as coverage-check §2c runs it."""
        src = tmp_path / "src"
        _write_text(src, "lib/config.py", PY_CONFIG)
        names = _write_json(tmp_path / "run" / "coverage.json", {"branch": "enumerated", "stale": stale})
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": entries})
        code = mod.main(["classify-stale", "--names", str(names), "--provenance", str(prov),
                         "--source-root", str(src)])
        return code, json.loads(capsys.readouterr().out)

    def test_every_entry_file_missing_is_fabricated(self, tmp_path: Path, capsys) -> None:
        code, out = self._run(tmp_path, capsys, ["ghost"], [
            {"export_name": "ghost", "source_file": "lib/gone.py", "source_line": 4},
            {"export_name": "ghost", "source_file": "lib/other.py", "source_line": 9}])
        assert code == 0
        assert out == [{"name": "ghost", "fabricated": True, "source": "lib/gone.py:4", "defined_at": None,
                        "declared_in": None, "reason": "not-defined", "entries": [
                            {"source_file": "lib/gone.py", "source_line": 4, "line_check": "file-missing",
                             "definition_lines": None},
                            {"source_file": "lib/other.py", "source_line": 9, "line_check": "file-missing",
                             "definition_lines": None}]}]

    def test_a_checked_file_without_the_name_is_fabricated(self, tmp_path: Path, capsys) -> None:
        _, [out] = self._run(tmp_path, capsys, ["ghost"], [
            {"export_name": "ghost", "source_file": "lib/config.py", "source_line": 11}])
        assert (out["fabricated"], out["reason"], out["entries"][0]["definition_lines"]) == (True, "not-defined", [])

    def test_one_entry_defining_the_name_is_not_fabricated(self, tmp_path: Path, capsys) -> None:
        _, [out] = self._run(tmp_path, capsys, ["search"], [
            {"export_name": "search", "source_file": "lib/gone.py", "source_line": 2},
            {"export_name": "search", "source_file": "lib/config.py", "source_line": 11}])
        assert (out["fabricated"], out["reason"], out["source"]) == (False, "defined", "lib/gone.py:2")
        assert [e["line_check"] for e in out["entries"]] == ["file-missing", "checked"]
        assert out["entries"][1]["definition_lines"] == [11]

    def test_no_entry_is_not_fabricated(self, tmp_path: Path, capsys) -> None:
        _, [out] = self._run(tmp_path, capsys, ["unmapped"], [
            {"export_name": "search", "source_file": "lib/config.py", "source_line": 11}])
        # the walk looked for it and found no declaration
        assert out == {"name": "unmapped", "fabricated": False, "source": None, "defined_at": None,
                       "declared_in": [], "reason": "no-entry", "entries": []}

    def test_an_unchecked_entry_is_not_fabricated(self, tmp_path: Path, capsys) -> None:
        _write_text(tmp_path / "src", "lib.rs", "pub fn add() {}\n")
        _, out = self._run(tmp_path, capsys, ["config", "add"], [
            {"export_name": "config", "source_file": "lib/config.py", "source_line": 1, "export_type": "module"},
            {"export_name": "add", "source_file": "lib.rs", "source_line": 1}])
        assert [(o["name"], o["fabricated"], o["reason"], o["entries"][0]["line_check"]) for o in out] == [
            ("config", False, "unchecked", "skipped-export-type"),
            ("add", False, "unchecked", "skipped-language")]

    def test_a_file_less_entry_alone_is_unchecked(self, tmp_path: Path, capsys) -> None:
        # update-skill writes an `unknown` NEW_EXPORT's entry with no source_file or source_line
        _, out = self._run(tmp_path, capsys, ["ghost", "spectre"], [
            {"export_name": "ghost", "export_type": "function"},
            {"export_name": "spectre", "source_file": None, "source_line": None}])
        assert out == [
            {"name": "ghost", "fabricated": False, "source": None, "defined_at": None, "declared_in": [],
             "reason": "unchecked",
             "entries": [{"source_file": None, "source_line": None, "line_check": "no-file",
                          "definition_lines": None}]},
            {"name": "spectre", "fabricated": False, "source": None, "defined_at": None, "declared_in": [],
             "reason": "unchecked",
             "entries": [{"source_file": None, "source_line": None, "line_check": "no-file",
                          "definition_lines": None}]}]

    @pytest.mark.parametrize("file_less_first", [True, False], ids=["file-less-first", "file-less-last"])
    def test_a_file_less_entry_beside_a_missing_file(self, tmp_path: Path, capsys, file_less_first: bool) -> None:
        """A file-less entry neither proves the name fabricated nor clears it, and its place changes nothing:
        the name is unchecked, at the citation of the entry that has a file."""
        entries = [{"export_name": "ghost", "source_file": "lib/gone.py", "source_line": 4},
                   {"export_name": "ghost", "source_file": "", "source_line": None}]
        _, [out] = self._run(tmp_path, capsys, ["ghost"], entries[::-1] if file_less_first else entries)
        assert (out["fabricated"], out["reason"], out["source"]) == (False, "unchecked", "lib/gone.py:4")
        assert sorted(e["line_check"] for e in out["entries"]) == ["file-missing", "no-file"]

    def test_a_file_less_entry_beside_a_defining_file(self, tmp_path: Path, capsys) -> None:
        _, [out] = self._run(tmp_path, capsys, ["search"], [
            {"export_name": "search"},
            {"export_name": "search", "source_file": "lib/config.py", "source_line": 11}])
        assert (out["fabricated"], out["reason"], out["source"]) == (False, "defined", "lib/config.py:11")

    def test_the_source_is_the_file_alone_when_the_line_is_not_a_number(self, tmp_path: Path, capsys) -> None:
        _, [out] = self._run(tmp_path, capsys, ["ghost"], [
            {"export_name": "ghost", "source_file": "lib/gone.py", "source_line": "near the top"}])
        assert (out["fabricated"], out["source"]) == (True, "lib/gone.py")

    def test_the_names_are_raw_and_each_once(self, tmp_path: Path, capsys) -> None:
        # a bare array of names, a repeat and a dotted name whose last segment is defined
        src = tmp_path / "src"
        _write_text(src, "m.py", "class App:\n    def update(self):\n        pass\n")
        names = _write_json(tmp_path / "names.json", ["App.update", "App.update", "update"])
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": [
            {"export_name": "App.update", "source_file": "m.py", "source_line": 2}]})
        code = mod.main(["classify-stale", "--names", str(names), "--provenance", str(prov),
                         "--source-root", str(src)])
        out = json.loads(capsys.readouterr().out)
        assert code == 0
        assert [(o["name"], o["reason"]) for o in out] == [("App.update", "defined"), ("update", "no-entry")]

    def test_output_file(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        names = _write_json(tmp_path / "coverage.json", {"stale": ["ghost"]})
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": [
            {"export_name": "ghost", "source_file": "gone.py", "source_line": 1}]})
        out = tmp_path / "run" / "stale.json"
        out.parent.mkdir()
        result = _run_cli("classify-stale", "--names", str(names), "--provenance", str(prov),
                          "--source-root", str(src), "-o", str(out))
        assert result.returncode == 0 and result.stdout == "", result.stderr
        assert json.loads(out.read_bytes())[0]["fabricated"] is True

    @pytest.mark.parametrize("names, prov, root, message", [
        ({"stale": "ghost"}, {"entries": []}, "src", "--names must hold"),
        ({"branch": "scalar"}, {"entries": []}, "src", "--names must hold"),
        ("not json", {"entries": []}, "src", "malformed JSON"),
        (["ghost"], ["not", "an", "object"], "src", "must be a JSON object"),
        (["ghost"], {"entries": []}, "nope", "source root not found"),
    ], ids=["stale-not-a-list", "no-stale", "malformed-names", "map-not-an-object", "no-source-root"])
    def test_bad_input_exit_2(self, tmp_path: Path, names, prov, root, message) -> None:
        (tmp_path / "src").mkdir()
        names_path = tmp_path / "names.json"
        if isinstance(names, str):
            names_path.write_bytes(names.encode("utf-8"))
        else:
            _write_json(names_path, names)
        prov_path = _write_json(tmp_path / "provenance-map.json", prov)
        result = _run_cli("classify-stale", "--names", str(names_path), "--provenance", str(prov_path),
                          "--source-root", str(tmp_path / root))
        assert result.returncode == 2
        assert result.stdout == "" and message in result.stderr, result.stderr

    def test_a_missing_names_file_exit_2(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": []})
        result = _run_cli("classify-stale", "--names", str(tmp_path / "nope.json"), "--provenance", str(prov),
                          "--source-root", str(tmp_path / "src"))
        assert result.returncode == 2 and "names not found" in result.stderr


# --------------------------------------------------------------------------
# classify-stale: defined_at, the documented-extra lookup (#678)
# --------------------------------------------------------------------------

# A package whose map's one entry cites `pkg/main.py`: the walk root is `pkg/`.
PKG = {"pkg/__init__.py": "from .main import main\n", "pkg/main.py": "def main():\n    pass\n"}
MAIN_ENTRY = {"export_name": "main", "source_file": "pkg/main.py", "source_line": 1}
# An entry of a TS/JS file outside every package: the map then cites both families.
TS_ENTRY = {"export_name": "y", "source_file": "pkg/y.ts", "source_line": 1}


def _defined_at(tmp_path: Path, capsys, files: dict[str, str], stale: list[str],
                entries: list[dict] | None = None) -> dict[str, str | None]:
    """classify-stale over `files` (below src/), as coverage-check §2c runs it: name -> defined_at."""
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        _write_text(src, rel, text)
    names = _write_json(tmp_path / "run" / "coverage.json", {"branch": "enumerated", "stale": stale})
    prov = _write_json(tmp_path / "provenance-map.json", {"entries": [MAIN_ENTRY] if entries is None else entries})
    code = mod.main(["classify-stale", "--names", str(names), "--provenance", str(prov), "--source-root", str(src)])
    assert code == 0
    return {o["name"]: o["defined_at"] for o in json.loads(capsys.readouterr().out)}


def _declares(rel: str) -> str:
    return "class X:\n    pass\n" if rel.endswith(".py") else "export class X {}\n"


class TestDefinedAt:
    """Where the source declares a stale name that is not fabricated: a documented extra to test-skill."""

    def test_an_extra_with_an_entry_is_at_its_cited_declaration(self, tmp_path: Path, capsys) -> None:
        files = {**PKG, "pkg/tasks/task.py": "class Task:\n    pass\n"}
        entries = [MAIN_ENTRY, {"export_name": "Task", "source_file": "pkg/tasks/task.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, files, ["Task"], entries) == {"Task": "pkg/tasks/task.py:1"}

    def test_an_extra_with_no_entry_is_found_in_the_walk(self, tmp_path: Path, capsys) -> None:
        # the cognee shape: names the package root re-exports from a nested package, with no entry of their own
        files = {
            **PKG,
            "pkg/__init__.py": "from .main import main\nfrom .modules.pipelines import Task, run_tasks\n",
            "pkg/modules/pipelines/__init__.py": "from .tasks.task import Task\nfrom .operations import run_tasks\n",
            "pkg/modules/pipelines/tasks/task.py": "from typing import Any\n\n\nclass Task:\n    pass\n",
            "pkg/modules/pipelines/operations.py": "import asyncio\n\n\nasync def run_tasks(tasks):\n    pass\n",
            "pkg/models/data_point.py": "import uuid\n\n\nclass DataPoint:\n    id: uuid.UUID\n",
        }
        out = _defined_at(tmp_path, capsys, files, ["Task", "run_tasks", "DataPoint"])
        assert out == {"Task": "pkg/modules/pipelines/tasks/task.py:4",
                       "run_tasks": "pkg/modules/pipelines/operations.py:4",
                       "DataPoint": "pkg/models/data_point.py:4"}

    @pytest.mark.parametrize("rel, text, line", [
        ("pkg/m.py", "from .base import Base\n\nX = Base()\n", 3),
        ("pkg/m.py", "X: int = 1\n", 1),
        ("pkg/m.py", "X: int\n", 1),
        ("pkg/m.py", "A, X = 1, 2\n", 1),
        ("pkg/m.py", "type X = int\n", 1),
        ("pkg/m.py", "async def X():\n    pass\n", 1),
        ("pkg/m.py", "from .impl import Impl as X\n", 1),
        ("pkg/m.py", "import json as X\n", 1),
        ("pkg/m.py", "from .impl import (\n    a,\n    Impl as X,\n)\n", 3),
        ("pkg/m.py", "from .impl import X\n\n\nclass X(X):\n    pass\n", 4),
        ("pkg/m.py", "class X:\n    pass\n\n\nX = 1\n", 1),
        ("pkg/m.ts", "export class X {}\n", 1),
        ("pkg/m.ts", "export default class X {}\n", 1),
        ("pkg/m.ts", "export declare const X: number;\n", 1),
        ("pkg/m.ts", "export const a = 1,\n  X = 2;\n", 2),
        ("pkg/m.ts", "export { impl as X } from './impl';\n", 1),
        ("pkg/m.ts", "export { default as X } from './impl';\n", 1),
        ("pkg/m.ts", "export * as X from './impl';\n", 1),
        ("pkg/m.js", "exports.X = function () {};\n", 1),
        ("pkg/m.js", "const X = requireAll('./x');\n", 1),
        ("pkg/m.js", "module.exports = {\n  X: impl,\n};\n", 2),
        ("pkg/m.js", "module.exports = {\n  X() {},\n};\n", 2),
    ], ids=["assignment", "annotated", "annotation-only", "target-list", "type-alias", "async-def", "from-as",
            "import-as", "parenthesized-as", "after-its-import", "first-of-two", "ts-class", "export-default-class",
            "declare-const", "later-declarator", "export-list-as", "default-as", "export-star-as", "exports-dot",
            "a-call-named-like-require", "module-exports-key", "module-exports-method"])
    def test_a_column_0_declaration_counts(self, tmp_path: Path, capsys, rel: str, text: str, line: int) -> None:
        files = {**PKG, rel: text}
        assert _defined_at(tmp_path, capsys, files, ["X"], [MAIN_ENTRY, TS_ENTRY]) == {"X": f"{rel}:{line}"}

    @pytest.mark.parametrize("rel, text", [
        ("pkg/m.py", "from .models import *\n"),
        ("pkg/m.py", "from pydantic import X\n"),
        ("pkg/m.py", "import X\n"),
        ("pkg/m.py", "from .impl import (\n    a,\n    X,\n)\n"),
        ("pkg/m.py", "from .impl import X as X\n"),
        ("pkg/m.py", "import pkg.impl.X as X\n"),
        ("pkg/m.py", "def build():\n    X = 1\n    return X\n"),
        ("pkg/m.py", "try:\n    from fast import X\nexcept ImportError:\n    class X:\n        pass\n"),
        ("pkg/m.py", '"""Docs.\n\nX: the thing.\n"""\n'),
        ("pkg/m.py", "X = (\n"),  # does not tokenize: every line would be a candidate
        ("pkg/m.ts", "import { X } from './x';\n"),
        ("pkg/m.ts", "export { X } from './x';\n"),
        ("pkg/m.ts", "export { X as X } from './x';\n"),
        ("pkg/m.ts", "export {\n  X,\n};\n"),
        ("pkg/m.ts", "export default X;\n"),
        ("pkg/m.ts", "export import X = Impl.X;\n"),
        ("pkg/m.ts", "// export class X {}\n"),
        ("pkg/m.ts", "namespace N {\n  export const X = 1;\n}\n"),
        ("pkg/m.js", "module.exports = { X };\n"),
        ("pkg/m.js", "const X = require('./x');\n"),
        ("pkg/m.ts", "const X: Mod = require('./x');\n"),
        ("pkg/m.js", "const a = 1, X = require('./x');\n"),
        ("pkg/m.js", "const X =\n  require('./x');\n"),
        ("pkg/m.js", "exports.X = require('./x');\n"),
        ("pkg/m.js", "module.exports.X = require('./x').X;\n"),
        ("pkg/m.js", "exports.X =\n  require('./x');\n"),
        ("pkg/m.js", "module.exports = {\n  X: require('./x'),\n};\n"),
        ("pkg/m.js", "module.exports = { X: require('./x') };\n"),
        ("pkg/m.mjs", "export const X = await import('./x');\n"),
        ("pkg/m.mjs", "const X = (await import('./x')).default;\n"),
        ("pkg/m.mjs", "const X = (\n  await import('./x')\n).default;\n"),
        ("pkg/m.js", "const X = import('./x');\n"),
        ("pkg/m.ts", "const X: () => void = require('./x');\n"),
        ("pkg/m.js", "const X = __importDefault(require('./x'));\n"),
        ("pkg/m.js", "exports.X = _interopRequireDefault(require('./x'));\n"),
        ("pkg/m.js", "const X = tslib.__importStar(\n  require('./x'));\n"),
        ("pkg/m.js", "const a = 1,\n  X = require('./x');\n"),
        ("pkg/m.js", "export const\n  X = require('./x');\n"),
        ("pkg/m.js", "class A {\n  X() {}\n}\n"),
    ], ids=["star-import", "from-import", "import", "parenthesized-import", "from-as-same-name",
            "import-as-same-name", "indented-local", "try-block", "docstring", "untokenizable", "ts-import",
            "export-list", "export-list-as-same-name", "export-list-lines", "export-default", "export-import",
            "comment", "namespace-member", "shorthand-key", "require", "annotated-require",
            "later-declarator-require", "line-broken-require", "exports-dot-require", "module-exports-dot-require",
            "line-broken-exports-require", "object-key-require", "inline-object-key-require", "await-import",
            "parenthesized-await-import", "line-broken-await-import", "dynamic-import", "arrow-typed-require",
            "import-default-helper", "interop-helper", "line-broken-helper", "continuation-line-require",
            "split-declaration-require", "class-member"])
    def test_anything_else_is_no_declaration(self, tmp_path: Path, capsys, rel: str, text: str) -> None:
        files = {**PKG, rel: text}
        assert _defined_at(tmp_path, capsys, files, ["X"], [MAIN_ENTRY, TS_ENTRY]) == {"X": None}

    @pytest.mark.parametrize("rel", [
        "pkg/tests/m.py", "pkg/test/m.py", "pkg/__tests__/m.js", "pkg/spec/m.ts", "pkg/Tests/m.py",
        "pkg/testing/m.py", "pkg/fixtures/m.py", "pkg/__mocks__/m.js",
        "pkg/vendor/m.py", "pkg/_vendor/m.py", "pkg/third_party/m.py",
        "pkg/examples/m.py", "pkg/docs/m.py", "pkg/benchmarks/m.py",
        "pkg/node_modules/m.js", "pkg/bower_components/m.js", "pkg/site-packages/m.py", "pkg/env/m.py",
        "pkg/venv/m.py", "pkg/build/m.py", "pkg/dist/m.js", "pkg/esm/m.js", "pkg/cjs/m.js", "pkg/umd/m.js",
        "pkg/.hidden/m.py",
        "pkg/test_m.py", "pkg/m_test.py", "pkg/m.test.ts", "pkg/m.spec.js", "pkg/conftest.py",
        "pkg/jest.config.js", "pkg/vitest.config.ts", "pkg/m.min.js", "pkg/M.MIN.JS",
        "other/m.py", "m.py",
    ], ids=lambda rel: rel.replace("/", "-"))
    def test_a_skipped_place_is_never_walked(self, tmp_path: Path, capsys, rel: str) -> None:
        # `other/m.py` and `m.py` lie outside `pkg/`, the walk root
        files = {**PKG, rel: _declares(rel)}
        assert _defined_at(tmp_path, capsys, files, ["X"], [MAIN_ENTRY, TS_ENTRY]) == {"X": None}

    @pytest.mark.parametrize("rel", ["pkg/lib/m.py", "pkg/src/lib/m.ts", "pkg/library/m.js"])
    def test_lib_is_walked(self, tmp_path: Path, capsys, rel: str) -> None:
        files = {**PKG, rel: _declares(rel)}
        assert _defined_at(tmp_path, capsys, files, ["X"], [MAIN_ENTRY, TS_ENTRY]) == {"X": f"{rel}:1"}

    def test_the_skips_are_judged_below_the_walk_root(self, tmp_path: Path, capsys) -> None:
        # the source root itself sits in a tests/ folder, and the walk root in an examples/ one
        files = {"examples/pkg/__init__.py": "", "examples/pkg/main.py": "def main():\n    pass\n",
                 "examples/pkg/m.py": "class X:\n    pass\n"}
        entries = [{"export_name": "main", "source_file": "examples/pkg/main.py", "source_line": 1}]
        assert _defined_at(tmp_path / "tests", capsys, files, ["X"], entries) == {"X": "examples/pkg/m.py:1"}

    def test_a_cited_file_in_a_skipped_place_is_not_read_either(self, tmp_path: Path, capsys) -> None:
        files = {**PKG, "pkg/tests/m.py": "class X:\n    pass\n"}
        entries = [MAIN_ENTRY, {"export_name": "X", "source_file": "pkg/tests/m.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, files, ["X"], entries) == {"X": None}

    def test_clustered_entries_widen_to_the_package_root(self, tmp_path: Path, capsys) -> None:
        # every entry under cognee/api/v1/: the walk still reads cognee/modules/
        files = {"cognee/__init__.py": "", "cognee/api/__init__.py": "", "cognee/api/v1/__init__.py": "",
                 "cognee/api/v1/add/__init__.py": "", "cognee/api/v1/add/add.py": "async def add(data):\n    pass\n",
                 "cognee/api/v1/search/search.py": "async def search(q):\n    pass\n",
                 "cognee/modules/pipelines/task.py": "class Task:\n    pass\n"}
        entries = [{"export_name": "add", "source_file": "cognee/api/v1/add/add.py", "source_line": 1},
                   {"export_name": "search", "source_file": "cognee/api/v1/search/search.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, files, ["Task"], entries) == {"Task": "cognee/modules/pipelines/task.py:1"}

    def test_an_entry_outside_every_package_is_left_out(self, tmp_path: Path, capsys) -> None:
        # a script and a setup.py beside the package do not widen the walk to the source root
        files = {**PKG, "scripts/tool.py": "def tool():\n    pass\n", "setup.py": "setup()\n",
                 "other/__init__.py": "", "other/x.py": "class X:\n    pass\n",
                 "pkg/sub/y.py": "class Y:\n    pass\n"}
        entries = [MAIN_ENTRY, {"export_name": "tool", "source_file": "scripts/tool.py", "source_line": 1},
                   {"export_name": "setup", "source_file": "setup.py", "source_line": 1}]
        # X lives in a sibling package, Y in the package the entries cite
        assert _defined_at(tmp_path, capsys, files, ["X", "Y"], entries) == {"X": None, "Y": "pkg/sub/y.py:1"}

    def test_a_stray_init_at_the_source_root_makes_no_package_of_the_tree(self, tmp_path: Path, capsys) -> None:
        # the source root's own __init__.py: the script beside the package stays outside every package
        files = {**PKG, "__init__.py": "", "scripts/tool.py": "def tool():\n    pass\n",
                 "other/__init__.py": "", "other/x.py": "class X:\n    pass\n",
                 "pkg/sub/y.py": "class Y:\n    pass\n"}
        entries = [MAIN_ENTRY, {"export_name": "tool", "source_file": "scripts/tool.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, files, ["X", "Y"], entries) == {"X": None, "Y": "pkg/sub/y.py:1"}

    def test_a_cited_file_outside_every_package_is_read(self, tmp_path: Path, capsys) -> None:
        files = {**PKG, "scripts/tool.py": "def tool():\n    pass\n"}
        entries = [MAIN_ENTRY, {"export_name": "tool", "source_file": "scripts/tool.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, files, ["tool"], entries) == {"tool": "scripts/tool.py:1"}

    def test_with_no_entry_in_a_package_the_walk_reads_the_source_root(self, tmp_path: Path, capsys) -> None:
        files = {"lib/a/one.py": "", "lib/b/two.py": "", "lib/c/X.py": "class X:\n    pass\n",
                 "elsewhere/y.py": "class Y:\n    pass\n"}
        entries = [{"export_name": n, "source_file": f, "source_line": 1}
                   for n, f in (("one", "lib/a/one.py"), ("two", "lib/b/two.py"))]
        assert _defined_at(tmp_path, capsys, files, ["X", "Y"], entries) == {"X": "lib/c/X.py:1",
                                                                             "Y": "elsewhere/y.py:1"}

    def test_entries_in_two_packages_walk_the_folder_they_share(self, tmp_path: Path, capsys) -> None:
        files = {"src/a/__init__.py": "", "src/a/one.py": "", "src/b/__init__.py": "", "src/b/two.py": "",
                 "src/b/deep/x.py": "class X:\n    pass\n", "tools/x.py": "class Y:\n    pass\n"}
        entries = [{"export_name": n, "source_file": f, "source_line": 1}
                   for n, f in (("one", "src/a/one.py"), ("two", "src/b/two.py"))]
        assert _defined_at(tmp_path, capsys, files, ["X", "Y"], entries) == {"X": "src/b/deep/x.py:1", "Y": None}

    def test_a_folder_that_is_gone_starts_the_walk_above_it(self, tmp_path: Path, capsys) -> None:
        files = {**PKG, "pkg/c/x.py": "class X:\n    pass\n"}
        entries = [{"export_name": "gone", "source_file": "pkg/gone/deeper/g.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, files, ["X"], entries) == {"X": "pkg/c/x.py:1"}

    def test_a_typescript_walk_root_is_the_nearest_package_json(self, tmp_path: Path, capsys) -> None:
        files = {"package.json": "{}", "packages/a/package.json": "{}",
                 "packages/a/src/index.ts": "export function run() {}\n",
                 "packages/a/lib/task.ts": "export class Task {}\n",
                 "packages/b/package.json": "{}", "packages/b/src/other.ts": "export class Other {}\n"}
        entries = [{"export_name": "run", "source_file": "packages/a/src/index.ts", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, files, ["Task", "Other"], entries) == {
            "Task": "packages/a/lib/task.ts:1", "Other": None}

    def test_a_homonym_needs_a_cited_file(self, tmp_path: Path, capsys) -> None:
        files = {**PKG, "pkg/a.py": "class Config:\n    pass\n", "pkg/b.py": "\nConfig = dict\n",
                 "pkg/c.py": "from .a import Config\n"}
        # two walked files declare it: no single declaration
        assert _defined_at(tmp_path, capsys, files, ["Config"]) == {"Config": None}
        # a cited file that declares it settles it
        cited = [MAIN_ENTRY, {"export_name": "Config", "source_file": "pkg/b.py", "source_line": 2}]
        assert _defined_at(tmp_path, capsys, files, ["Config"], cited) == {"Config": "pkg/b.py:2"}
        # a cited file that only imports it does not
        cited = [MAIN_ENTRY, {"export_name": "Config", "source_file": "pkg/c.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, files, ["Config"], cited) == {"Config": None}

    @pytest.mark.parametrize("rel, text, name, line", [
        ("pkg/low_level.py", "from .models import DataPoint\n", "low_level", 1),
        ("pkg/tools/__init__.py", "", "tools", 1),
        ("pkg/web/helpers.ts", "export const a = 1;\n", "helpers", 1),
        ("pkg/web/widgets/index.js", "module.exports = {};\n", "widgets", 1),
        ("pkg/ops/run_tasks.py", "import asyncio\n\n\nasync def run_tasks(tasks):\n    pass\n", "run_tasks", 4),
    ], ids=["module", "package", "ts-module", "js-index", "a-line-of-it-first"])
    def test_a_module_or_package_declares_its_name(self, tmp_path: Path, capsys, rel: str, text: str, name: str,
                                                    line: int) -> None:
        files = {**PKG, rel: text}
        assert _defined_at(tmp_path, capsys, files, [name], [MAIN_ENTRY, TS_ENTRY]) == {name: f"{rel}:{line}"}

    @pytest.mark.parametrize("rel", ["pkg/low_level.pyi", "pkg/low_level.txt", "pkg/low_level.d.ts",
                                     "pkg/tests/low_level.py", "pkg/low_level/__main__.py", "low_level.py"])
    def test_any_other_file_is_no_module(self, tmp_path: Path, capsys, rel: str) -> None:
        files = {**PKG, rel: ""}
        assert _defined_at(tmp_path, capsys, files, ["low_level"], [MAIN_ENTRY, TS_ENTRY]) == {"low_level": None}

    def test_declared_in_lists_every_walked_declaration(self, tmp_path: Path, capsys) -> None:
        files = {**PKG, "pkg/models/Task.py": "from .base import Base\n\n\nclass Task(Base):\n    pass\n",
                 "pkg/tasks/task.py": "class Task:\n    pass\n", "pkg/tasks/__init__.py": "from .task import Task\n",
                 "pkg/tools.py": "", "pkg/tools/__init__.py": "", "pkg/one.py": "class One:\n    pass\n",
                 "pkg/app.py": "def update():\n    pass\n"}
        entries = [MAIN_ENTRY, {"export_name": "One", "source_file": "pkg/one.py", "source_line": 1},
                   {"export_name": "App.update", "source_file": "pkg/app.py", "source_line": 1},
                   {"export_name": "Ghost", "source_file": "pkg/gone.py", "source_line": 1}]
        src = tmp_path / "src"
        for rel, text in files.items():
            _write_text(src, rel, text)
        names = _write_json(tmp_path / "names.json", ["Task", "tools", "Nowhere", "One", "App.update", "Ghost"])
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": entries})
        assert mod.main(["classify-stale", "--names", str(names), "--provenance", str(prov),
                         "--source-root", str(src)]) == 0
        out = {o["name"]: (o["defined_at"], o["declared_in"]) for o in json.loads(capsys.readouterr().out)}
        assert out == {
            # a homonym: every walked declaration, sorted, and no defined_at
            "Task": (None, ["pkg/models/Task.py:4", "pkg/tasks/task.py:1"]),
            # a module beside a package of the same name
            "tools": (None, ["pkg/tools.py:1", "pkg/tools/__init__.py:1"]),
            "Nowhere": (None, []),
            # a cited hit needs no walk; a dotted or fabricated name is not looked up
            "One": ("pkg/one.py:1", None), "App.update": (None, None), "Ghost": (None, None),
        }

    def test_a_stub_and_its_implementation_are_one_declaring_file(self, tmp_path: Path, capsys) -> None:
        files = {**PKG, "pkg/task.py": "\n\nclass Task:\n    pass\n", "pkg/task.pyi": "class Task: ...\n",
                 "pkg/web/client.js": "class Client {}\nexports.Client = Client;\n",
                 "pkg/web/client.d.ts": "export declare class Client {}\n",
                 "pkg/web/only.d.ts": "export declare class Typed {}\n"}
        src = tmp_path / "src"
        for rel, text in files.items():
            _write_text(src, rel, text)
        names = _write_json(tmp_path / "names.json", ["Task", "Client", "Typed"])
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": [MAIN_ENTRY, TS_ENTRY]})
        assert mod.main(["classify-stale", "--names", str(names), "--provenance", str(prov),
                         "--source-root", str(src)]) == 0
        out = {o["name"]: (o["defined_at"], o["declared_in"]) for o in json.loads(capsys.readouterr().out)}
        # the implementation stands for both; a stub with no implementation beside it stays
        assert out == {"Task": ("pkg/task.py:3", ["pkg/task.py:3"]),
                       "Client": ("pkg/web/client.js:1", ["pkg/web/client.js:1"]),
                       "Typed": ("pkg/web/only.d.ts:1", ["pkg/web/only.d.ts:1"])}

    def test_an_untokenizable_file_that_holds_the_name_makes_it_ambiguous(self, tmp_path: Path, capsys) -> None:
        files = {**PKG, "pkg/a.py": "class Task:\n    pass\n", "pkg/broken.py": "class Task(\n",
                 "pkg/c.py": "class Other:\n    pass\n", "pkg/d.py": "Other = (\n"}
        src = tmp_path / "src"
        for rel, text in files.items():
            _write_text(src, rel, text)
        names = _write_json(tmp_path / "names.json", ["Task", "Other", "Plain"])
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": [MAIN_ENTRY]})
        _write_text(src, "pkg/e.py", "class Plain:\n    pass\n")
        assert mod.main(["classify-stale", "--names", str(names), "--provenance", str(prov),
                         "--source-root", str(src)]) == 0
        out = {o["name"]: (o["defined_at"], o["declared_in"]) for o in json.loads(capsys.readouterr().out)}
        # broken.py may declare Task and d.py Other; neither holds Plain, which stays unique
        assert out == {"Task": (None, ["pkg/a.py:1"]), "Other": (None, ["pkg/c.py:1"]),
                       "Plain": ("pkg/e.py:1", ["pkg/e.py:1"])}

    def test_only_the_families_the_map_cites_are_read(self, tmp_path: Path, capsys) -> None:
        files = {**PKG, "pkg/ui/task.ts": "export interface Task {}\n", "pkg/lib.rs": "pub struct Task;\n"}
        # a Python map never reads a TS/JS file
        assert _defined_at(tmp_path, capsys, files, ["Task"]) == {"Task": None}
        # a map that cites no Python or TS/JS file reads nothing
        rust = [{"export_name": "lib", "source_file": "pkg/lib.rs", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, {"pkg/task.py": "class Task:\n    pass\n"}, ["Task"], rust) == \
            {"Task": None}

    def test_a_fabricated_name_is_not_looked_up(self, tmp_path: Path, capsys) -> None:
        files = {**PKG, "pkg/other.py": "class Ghost:\n    pass\n"}
        entries = [MAIN_ENTRY, {"export_name": "Ghost", "source_file": "pkg/gone.py", "source_line": 3}]
        src = tmp_path / "src"
        for rel, text in files.items():
            _write_text(src, rel, text)
        names = _write_json(tmp_path / "names.json", ["Ghost"])
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": entries})
        mod.main(["classify-stale", "--names", str(names), "--provenance", str(prov), "--source-root", str(src)])
        [out] = json.loads(capsys.readouterr().out)
        assert (out["fabricated"], out["defined_at"]) == (True, None)

    def test_a_dotted_name_is_not_looked_up(self, tmp_path: Path, capsys) -> None:
        files = {**PKG, "pkg/app.py": "def update():\n    pass\n"}
        entries = [MAIN_ENTRY, {"export_name": "App.update", "source_file": "pkg/app.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, files, ["App.update"], entries) == {"App.update": None}

    def test_the_answer_is_deterministic(self, tmp_path: Path, capsys) -> None:
        src = tmp_path / "src"
        for rel, text in (("pkg/z/x.py", "\n\nclass X:\n    pass\n\n\nX = 2\n"), ("pkg/b/y.py", "class Y:\n    pass\n"),
                          ("pkg/a/y.py", "Y = 1\n"), *PKG.items()):  # written out of order
            _write_text(src, rel, text)
        expected = {"X": "pkg/z/x.py:3", "Y": None}
        assert _defined_at(tmp_path, capsys, {}, ["X", "Y"]) == expected == _defined_at(tmp_path, capsys, {},
                                                                                       ["Y", "X"])
        # a cited file comes before the walk, written however the map writes it
        cited = [MAIN_ENTRY, {"export_name": "Y", "source_file": "./pkg/b/y.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, {}, ["Y"], cited) == {"Y": "pkg/b/y.py:1"}

    def test_a_cited_path_outside_the_root_is_never_read(self, tmp_path: Path, capsys) -> None:
        outside = _write_text(tmp_path, "outside/task.py", "class Task:\n    pass\n")
        for cited in ("../outside/task.py", outside.as_posix(), "pkg/../../outside/task.py"):
            entries = [MAIN_ENTRY, {"export_name": "Task", "source_file": cited, "source_line": 1}]
            assert _defined_at(tmp_path, capsys, PKG, ["Task"], entries) == {"Task": None}, cited

    def test_the_walk_never_leaves_the_source_root(self, tmp_path: Path, capsys) -> None:
        # the map's only in-package entry lies outside the source root: the walk stays inside it
        _write_text(tmp_path, "outside/pkg/__init__.py", "")
        _write_text(tmp_path, "outside/pkg/m.py", "def m():\n    pass\n")
        _write_text(tmp_path, "outside/pkg/secret.py", "class Secret:\n    pass\n")
        src = tmp_path / "src"
        _write_text(src, "lib/plain.py", "VALUE = 1\n")
        names = _write_json(tmp_path / "names.json", ["Secret"])
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": [
            {"export_name": "m", "source_file": "../outside/pkg/m.py", "source_line": 1}]})
        assert mod.main(["classify-stale", "--names", str(names), "--provenance", str(prov),
                         "--source-root", str(src)]) == 0
        [out] = json.loads(capsys.readouterr().out)
        assert (out["defined_at"], out["declared_in"]) == (None, [])

    @pytest.mark.skipif(not hasattr(os, "symlink") or os.name == "nt", reason="needs POSIX symlinks")
    def test_a_symlink_anywhere_on_the_path_is_never_read(self, tmp_path: Path, capsys) -> None:
        outside = _write_text(tmp_path, "outside/task.py", "class Task:\n    pass\n")
        src = tmp_path / "src"
        for rel, text in {**PKG, "elsewhere/job.py": "class Job:\n    pass\n"}.items():
            _write_text(src, rel, text)
        (src / "pkg" / "task.py").symlink_to(outside)
        (src / "pkg" / "linked").symlink_to(outside.parent, target_is_directory=True)
        # a folder link that stays inside the source root is not followed either
        (src / "pkg" / "jobs").symlink_to(src / "elsewhere", target_is_directory=True)
        entries = [MAIN_ENTRY, {"export_name": "Task", "source_file": "pkg/task.py", "source_line": 1},
                   {"export_name": "Job", "source_file": "pkg/jobs/job.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, {}, ["Task", "Job"], entries) == {"Task": None, "Job": None}

    @pytest.mark.parametrize("error", [PermissionError, OSError, UnicodeDecodeError])
    def test_a_lookup_error_gives_null(self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch,
                                       error: type[Exception]) -> None:
        def fail(path: Path) -> str:
            if error is UnicodeDecodeError:
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
            raise error(13, "denied", str(path))

        monkeypatch.setattr(mod, "_read_source", fail)
        files = {**PKG, "pkg/task.py": "class Task:\n    pass\n"}
        entries = [MAIN_ENTRY, {"export_name": "Ghost", "source_file": "pkg/gone.py", "source_line": 1}]
        src = tmp_path / "src"
        for rel, text in files.items():
            _write_text(src, rel, text)
        names = _write_json(tmp_path / "names.json", ["Task", "Ghost"])
        prov = _write_json(tmp_path / "provenance-map.json", {"entries": entries})
        code = mod.main(["classify-stale", "--names", str(names), "--provenance", str(prov),
                         "--source-root", str(src)])
        out = json.loads(capsys.readouterr().out)
        # the exit code and the fabricated test stand; no name gets a defined_at
        assert code == 0
        assert [(o["name"], o["fabricated"], o["defined_at"]) for o in out] == [("Task", False, None),
                                                                                ("Ghost", True, None)]

    @pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                        reason="needs POSIX permissions that bind the user")
    def test_a_folder_the_walk_cannot_list_gives_null(self, tmp_path: Path, capsys) -> None:
        files = {**PKG, "pkg/task.py": "class Task:\n    pass\n", "pkg/locked/m.py": ""}
        src = tmp_path / "src"
        for rel, text in files.items():
            _write_text(src, rel, text)
        (src / "pkg" / "locked").chmod(0)
        try:
            assert _defined_at(tmp_path, capsys, {}, ["Task"]) == {"Task": None}
        finally:
            (src / "pkg" / "locked").chmod(0o755)

    def test_one_pass_reads_each_file_once(self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        reads: list[str] = []
        split: list[int] = []
        real_read, real_split = mod._read_source, mod._text_lines
        monkeypatch.setattr(mod, "_read_source", lambda path: reads.append(path.name) or real_read(path))
        monkeypatch.setattr(mod, "_text_lines", lambda text: split.append(1) or real_split(text))
        files = {**PKG, "pkg/a.py": "class A:\n    pass\n", "pkg/b.py": "from .a import A\n\n\nclass B:\n    pass\n",
                 "pkg/c.py": "value = 1\n"}
        # A's cited file only imports it: the walk reuses that file, and reads every other one once for A, B, C
        entries = [MAIN_ENTRY, {"export_name": "A", "source_file": "pkg/b.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, files, ["A", "B", "C"], entries) == {"A": "pkg/a.py:1",
                                                                                   "B": "pkg/b.py:4", "C": None}
        assert sorted(reads) == ["__init__.py", "a.py", "b.py", "c.py", "main.py"]
        # only the cited file and the one walked text that holds a name are split into lines
        assert len(split) == 2

    def test_a_cited_hit_needs_no_walk(self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        walks: list[int] = []
        real_tree = mod._DeclarationLookup._tree
        monkeypatch.setattr(mod._DeclarationLookup, "_tree", lambda self: walks.append(1) or real_tree(self))
        files = {**PKG, "pkg/a.py": "class A:\n    pass\n", "pkg/b.py": "class B:\n    pass\n"}
        entries = [MAIN_ENTRY, {"export_name": "A", "source_file": "pkg/a.py", "source_line": 1},
                   {"export_name": "B", "source_file": "pkg/b.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, files, ["A", "B"], entries) == {"A": "pkg/a.py:1", "B": "pkg/b.py:1"}
        assert walks == []
        assert _defined_at(tmp_path, capsys, files, ["A", "B", "C"], entries)["C"] is None
        assert walks == [1]  # one walk for every name a cited file did not settle

    def test_a_map_that_cites_no_file_walks_the_source_root(self, tmp_path: Path, capsys) -> None:
        files = {"pkg/models/data_point.py": "import uuid\n\n\nclass DataPoint:\n    pass\n",
                 "web/point.ts": "export interface WebPoint {}\n"}
        out = _defined_at(tmp_path, capsys, files, ["DataPoint", "WebPoint"], [{"export_name": "DataPoint"}])
        assert out == {"DataPoint": "pkg/models/data_point.py:4", "WebPoint": "web/point.ts:1"}

    def test_the_lookup_rules_are_opt_in(self, tmp_path: Path) -> None:
        # verify, fix and definition-lines keep the import, star-import, re-export and indented matches
        src = tmp_path / "src"
        _write_text(src, "m.py", "from x import *\n")
        _write_text(src, "n.py", "from x import X\n\n\ndef f():\n    X = 1\n")
        _write_text(src, "o.py", "from .x import X as X\n")
        _write_text(src, "r.js", "const X = require('./x');\n")
        _write_text(src, "q.js", "const a = 1, X = require('./x');\n")
        _write_text(src, "p.js", "const X =\n  require('./x');\n")
        _write_text(src, "s.js", "exports.X = require('./x');\n")
        _write_text(src, "t.ts", "export { X as X } from './x';\n")
        _write_text(src, "u.js", "module.exports = {\n  X: require('./x'),\n};\n")
        # the default-mode `require` declarator, as a statement, a later declarator or a broken line
        for rel in ("m.py", "n.py", "o.py", "r.js", "q.js", "p.js", "s.js", "t.ts"):
            assert mod.find_definition_lines(rel, "X", src) == [1], rel
        assert mod.find_definition_lines("u.js", "X", src) == [2]
        for rel in ("m.py", "n.py", "o.py", "r.js", "q.js", "p.js", "s.js", "t.ts", "u.js"):
            assert mod._definition_matches(rel, "X", src, declarations_only=True) == ([], set()), rel


class TestDeclaredLine:
    """declared_line: the defined_at rule for one file, public for skf-extraction-snapshot.py's
    baseline gaps (#682), and the rule the lookup itself runs."""

    @pytest.mark.parametrize("rel, text, name, line", [
        ("cognee/__init__.py", "from .version import get_cognee_version\n\n__version__ = get_cognee_version()\n",
         "__version__", 3),
        ("cognee/api/v1/__init__.py", "from cognee.api.v1.visualize import visualize_graph as visualize\n",
         "visualize", 1),
        ("pkg/m.py", "import os\n\n\nasync def add(x):\n    pass\n", "add", 4),
        ("pkg/m.ts", "export const a = 1;\nexport class X {}\n", "X", 2),
        # a module or package named after the name declares it at line 1
        ("cognee/api/v1/session/session.py", "def get_session():\n    pass\n", "session", 1),
        ("cognee/modules/pipelines/__init__.py", "from .tasks import Task\n", "pipelines", 1),
        ("pkg/widget/index.ts", "export const a = 1;\n", "widget", 1),
    ], ids=["dunder", "alias-that-renames", "async-def", "ts-class", "module", "package", "ts-package"])
    def test_a_declaration_gives_its_line(self, tmp_path: Path, rel: str, text: str, name: str, line: int) -> None:
        _write_text(tmp_path, rel, text)
        assert mod.declared_line(rel, name, tmp_path) == line
        # lines read already are not read again: the same answer for the file's segments
        lines = (tmp_path / rel).read_text(encoding="utf-8").split("\n")
        assert mod.declared_line(tuple(rel.split("/")), name, lines=lines) == line

    @pytest.mark.parametrize("rel, text, name", [
        ("pkg/m.py", "from .version import __version__\n", "__version__"),
        ("pkg/m.py", "from .models import *\n", "X"),
        ("pkg/m.py", "def outer():\n    X = 1\n", "X"),
        ("pkg/m.py", "# X = 1\n", "X"),
        ("pkg/m.ts", "export { X } from './x';\n", "X"),
        ("pkg/m.js", "const X = require('./x');\n", "X"),
        ("pkg/m.py", "class App:\n    def update(self):\n        pass\n", "App.update"),
        ("pkg/m.go", "func X() {}\n", "X"),
        ("pkg/m.py", "def run_startup_migrations():\n    pass\n", "run_migrations"),
    ], ids=["plain-import", "star-import", "indented-local", "comment", "export-list", "require-binding", "dotted",
            "no-rule-family", "removed"])
    def test_no_declaration_gives_none(self, tmp_path: Path, rel: str, text: str, name: str) -> None:
        _write_text(tmp_path, rel, text)
        assert mod.declared_line(rel, name, tmp_path) is None

    def test_a_file_it_cannot_read_or_outside_the_root_gives_none(self, tmp_path: Path) -> None:
        _write_text(tmp_path, "outside.py", "X = 1\n")
        root = tmp_path / "src"
        root.mkdir()
        assert mod.declared_line("pkg/gone.py", "X", root) is None
        assert mod.declared_line("../outside.py", "X", root) is None
        assert mod.declared_line(str(tmp_path / "outside.py"), "X", root) is None
        assert mod.declared_line("pkg/m.py", "", root) is None
        with pytest.raises(ValueError, match="source_root"):
            mod.declared_line("pkg/m.py", "X")

    def test_the_module_rule_is_optional(self, tmp_path: Path) -> None:
        # a removed function named after its file is no declaration without the module rule
        _write_text(tmp_path, "pkg/widget.py", "def other():\n    pass\n")
        assert mod.declared_line("pkg/widget.py", "widget", tmp_path) == 1
        assert mod.declared_line("pkg/widget.py", "widget", tmp_path, module_fallback=False) is None
        _write_text(tmp_path, "pkg/widget.py", "import os\n\n\ndef widget():\n    pass\n")
        assert mod.declared_line("pkg/widget.py", "widget", tmp_path, module_fallback=False) == 4

    @pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
    def test_a_symlinked_cited_file_is_not_read(self, tmp_path: Path) -> None:
        """The lookup's guards hold when declared_line reads the file: no
        symlink on its path (into the root or out of it), its real path
        inside the root, and no file the lookup skips."""
        outside = _write_text(tmp_path, "outside/secret.py", "X = 1\n")
        root = tmp_path / "src"
        inside = _write_text(root, "pkg/real.py", "X = 1\n")
        try:
            (root / "pkg" / "out.py").symlink_to(outside)
            (root / "pkg" / "in.py").symlink_to(inside)
            (root / "linked").symlink_to(root / "pkg", target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"cannot create a symlink: {exc}")
        assert mod.declared_line("pkg/real.py", "X", root) == 1
        for rel in ("pkg/out.py", "pkg/in.py", "linked/real.py"):
            assert mod.declared_line(rel, "X", root) is None, rel
        for rel in ("pkg/test_m.py", "pkg/conftest.py"):
            _write_text(root, rel, "X = 1\n")
            assert mod.declared_line(rel, "X", root) is None, rel

    def test_one_cache_reads_each_file_once(self, tmp_path: Path, monkeypatch) -> None:
        _write_text(tmp_path, "pkg/m.py", "A = 1\nB = 2\n")
        reads: list[Path] = []
        real = mod._read_lines
        monkeypatch.setattr(mod, "_read_lines", lambda path: reads.append(path) or real(path))
        cache = mod.SourceCache()
        assert [mod.declared_line("pkg/m.py", n, tmp_path, cache=cache) for n in ("A", "B", "C")] == [1, 2, None]
        assert len(reads) == 1

    def test_the_lookup_runs_it(self, tmp_path: Path, capsys) -> None:
        # classify-stale's defined_at for a cited file is declared_line's line
        files = {**PKG, "pkg/m.py": "import os\n\nX = 1\n"}
        entries = [MAIN_ENTRY, {"export_name": "X", "source_file": "pkg/m.py", "source_line": 1}]
        assert _defined_at(tmp_path, capsys, files, ["X"], entries) == {"X": "pkg/m.py:3"}
        assert mod.declared_line("pkg/m.py", "X", tmp_path / "src") == 3


class TestBaselineGaps:
    """baseline_gaps (#687): the map entries an extraction left out whose cited file still declares them, the one
    selection skf-extraction-snapshot.py and skf-build-change-manifest.py baseline-gaps both call."""

    # cognee's shape: the runner reports none of these, the diff would read each as deleted
    COGNEE = {
        "cognee/__init__.py": ("from .version import get_cognee_version\nfrom .api.v1 import visualize\n\n"
                               "__version__ = get_cognee_version()\n"),
        "cognee/api/v1/__init__.py": "from cognee.api.v1.visualize import visualize_graph as visualize\n",
        "cognee/api/v1/session/session.py": "def get_session():\n    pass\n",
        "cognee/modules/pipelines/__init__.py": "from .tasks import Task\n",
        "cognee/run_migrations.py": "async def run_migrations():\n    pass\n",
    }
    ENTRIES = [
        {"export_name": "__version__", "export_type": "variable", "source_file": "cognee/__init__.py"},
        {"export_name": "visualize", "export_type": "alias", "source_file": "cognee/api/v1/__init__.py"},
        {"export_name": "session", "export_type": "module", "source_file": "cognee/api/v1/session/session.py"},
        {"export_name": "pipelines", "export_type": "module", "source_file": "cognee/modules/pipelines/__init__.py"},
        {"export_name": "run_startup_migrations", "export_type": "async_function",
         "source_file": "cognee/run_migrations.py"},
    ]

    def _root(self, tmp_path: Path, files: dict) -> Path:
        for rel, text in files.items():
            _write_text(tmp_path, rel, text)
        return tmp_path

    def test_the_names_the_runner_leaves_out_and_a_real_deletion(self, tmp_path: Path) -> None:
        root = self._root(tmp_path, self.COGNEE)
        files = {e["source_file"] for e in self.ENTRIES}
        gaps, unchecked = mod.baseline_gaps({"entries": self.ENTRIES}, root, set(), files)
        assert [(g["name"], g["file"], g["line"], g["export_type"]) for g in gaps] == [
            ("__version__", "cognee/__init__.py", 4, "variable"),
            ("visualize", "cognee/api/v1/__init__.py", 1, "alias"),
            ("session", "cognee/api/v1/session/session.py", 1, "module"),
            ("pipelines", "cognee/modules/pipelines/__init__.py", 1, "module"),
        ]
        assert all(g["entry"] is None for g in gaps) and unchecked == []
        # run_startup_migrations is declared no more: no gap, so the diff reports it deleted

    def test_what_is_left_out(self, tmp_path: Path) -> None:
        root = self._root(tmp_path, {"pkg/a.py": "_x = 1\n_y = 2\n_z = 3\n_w = 4\nclass C:\n    m = 1\n",
                                     "pkg/b.py": "_q = 1\n"})
        entries = [
            {"export_name": "_x", "source_file": "pkg/a.py"},             # held under its name
            {"export_name": "_impl", "source_file": "pkg/a.py", "reexported_as": "_y"},  # held under its target
            {"export_name": "_z", "source_file": "pkg/a.py"},             # listed already
            {"export_name": "C.m", "source_file": "pkg/a.py"},            # dotted
            {"export_name": "_q", "source_file": "pkg/b.py"},             # a file not checked
            {"export_name": "_w", "source_file": ".\\pkg\\a.py"},         # the one gap, its path normalized
            {"export_name": "_w", "source_file": "pkg/a.py"},             # once per name and file
            {"export_name": "a", "export_type": "function", "source_file": "pkg/a.py"},  # no module rule
            "not an entry", {"export_name": 3, "source_file": "pkg/a.py"},
        ]
        gaps, unchecked = mod.baseline_gaps({"entries": entries}, root, {("_x", "pkg/a.py"), ("_y", "pkg/a.py")},
                                            {"pkg/a.py"}, {("_z", "pkg/a.py")})
        assert gaps == [{"name": "_w", "file": "pkg/a.py", "line": 4, "entry": None}] and unchecked == []

    def test_a_top_level_reexport_map_holds_the_target(self, tmp_path: Path) -> None:
        root = self._root(tmp_path, {"pkg/a.py": "_impl = 1\n"})
        prov = {"reexport_map": {"_impl": "Public"}, "entries": [{"export_name": "_impl", "source_file": "pkg/a.py"}]}
        assert mod.baseline_gaps(prov, root, {("Public", "pkg/a.py")}, {"pkg/a.py"}) == ([], [])
        assert mod.baseline_gaps(prov, root, set(), {"pkg/a.py"})[0][0]["name"] == "_impl"

    def test_another_language_is_unchecked(self, tmp_path: Path) -> None:
        root = self._root(tmp_path, {"src/lib.rs": "pub const _X: u8 = 1;\n", "web/a.ts": "export const _y = 1;\n"})
        entries = [{"export_name": "_X", "source_file": "src/lib.rs"}, {"export_name": "_y", "source_file": "web/a.ts"}]
        gaps, unchecked = mod.baseline_gaps({"entries": entries}, root, set(), {"src/lib.rs", "web/a.ts"})
        assert [(g["name"], g["line"]) for g in gaps] == [("_y", 1)] and "export_type" not in gaps[0]
        assert unchecked == [{"name": "_X", "file": "src/lib.rs", "export_type": None}]

    def test_a_file_the_lookup_will_not_read_and_a_dotted_module_are_unchecked(self, tmp_path: Path) -> None:
        """declared_line refuses a test file, a symlinked path and one outside the root, and a dotted module name
        has no declaring line: each is listed to read by eye rather than read as deleted. A file that is gone is
        neither (its entries are deleted), and a dotted member is left out as before."""
        root = self._root(tmp_path / "src", {"pkg/test_util.py": "_helper = 1\n", "pkg/real.py": "_x = 1\n",
                                             "pkg/api/v1/__init__.py": "", "outside.py": ""})
        (tmp_path / "elsewhere.py").write_text("_out = 1\n", encoding="utf-8")
        (root / "pkg" / "link.py").symlink_to(root / "pkg" / "real.py")
        entries = [
            {"export_name": "_helper", "export_type": "variable", "source_file": "pkg/test_util.py"},
            {"export_name": "_x", "source_file": "pkg/link.py"},
            {"export_name": "_out", "source_file": "../elsewhere.py"},
            {"export_name": "api.v1", "export_type": "module", "source_file": "pkg/api/v1/__init__.py"},
            {"export_name": "App.run", "export_type": "method", "source_file": "pkg/real.py"},
            {"export_name": "_gone", "source_file": "pkg/gone.py"},
        ]
        files = {"pkg/test_util.py", "pkg/link.py", "../elsewhere.py", "pkg/api/v1/__init__.py", "pkg/real.py",
                 "pkg/gone.py"}
        gaps, unchecked = mod.baseline_gaps({"entries": entries}, root, set(), files)
        assert gaps == []
        assert unchecked == [
            {"name": "_helper", "file": "pkg/test_util.py", "export_type": "variable"},
            {"name": "_x", "file": "pkg/link.py", "export_type": None},
            {"name": "_out", "file": "../elsewhere.py", "export_type": None},
            {"name": "api.v1", "file": "pkg/api/v1/__init__.py", "export_type": "module"},
        ]

    def test_no_entries(self, tmp_path: Path) -> None:
        assert mod.baseline_gaps({}, tmp_path, set(), {"x.py"}) == ([], [])
        assert mod.baseline_gaps({"entries": None}, tmp_path, set(), {"x.py"}) == ([], [])

    def test_one_cache_reads_each_file_once(self, tmp_path: Path, monkeypatch) -> None:
        root = self._root(tmp_path, {"pkg/m.py": "_a = 1\n_b = 2\n"})
        reads: list[Path] = []
        real = mod._read_lines
        monkeypatch.setattr(mod, "_read_lines", lambda path: reads.append(path) or real(path))
        entries = [{"export_name": n, "source_file": "pkg/m.py"} for n in ("_a", "_b", "_c")]
        gaps, _ = mod.baseline_gaps({"entries": entries}, root, set(), {"pkg/m.py"})
        assert [g["name"] for g in gaps] == ["_a", "_b"] and len(reads) == 1


class TestLookupSkipsPinnedToTheirSources:
    """Each skip set the defined_at lookup copies stays identical to the one it names."""

    @staticmethod
    def _source(script: str):
        path = REPO_ROOT / "src" / "shared" / "scripts" / script
        pin = importlib.util.spec_from_file_location("skf_pin_" + script[:-3].replace("-", "_"), path)
        source = importlib.util.module_from_spec(pin)
        pin.loader.exec_module(source)
        return source

    @pytest.mark.parametrize("script, name", [
        ("skf-resolve-authoritative-files.py", "EXCLUDED_DIR_NAMES"),
        ("skf-detect-language.py", "_VENDORED_SEGMENTS"),
        ("skf-disqualify-candidates.py", "TEST_FOLDERS"),
        ("skf-disqualify-candidates.py", "TEST_CONFIG_NAMES"),
        ("skf-disqualify-candidates.py", "TEST_CONFIG_PREFIXES"),
        ("skf-disqualify-candidates.py", "TEST_FILE_RE"),
        ("skf-extract-public-api.py", "PY_NON_CORE_TOPS"),
    ])
    def test_the_copy_matches(self, script: str, name: str) -> None:
        assert f"# Keep identical to {name} in {script}." in SCRIPT_PATH.read_text(encoding="utf-8")
        mine, theirs = getattr(mod, name), getattr(self._source(script), name)
        if isinstance(theirs, re.Pattern):
            mine, theirs = (mine.pattern, mine.flags), (theirs.pattern, theirs.flags)
        assert mine == theirs

    @pytest.mark.parametrize("filename", [
        "conftest.py", "pytest.ini", "jest.config.js", "Vitest.Config.ts", "karma.conf.js", "playwright.config.ts",
        "cypress.config.mjs", "test_m.py", "m_test.go", "m.test.ts", "m.spec.js", "m_spec.rb", "m.py", "index.ts",
        "testing.py", "contest.py",
    ])
    def test_a_test_file_is_what_disqualify_candidates_calls_one(self, filename: str) -> None:
        assert mod._lookup_skips_file(filename) is self._source("skf-disqualify-candidates.py")._is_test_file(filename)

    def test_the_walk_skips_each_copy_and_its_own_folders(self) -> None:
        assert mod.LOOKUP_EXTRA_FOLDERS == {"_vendor", "testing", "fixtures", "__mocks__", "site-packages", "env",
                                            "bower_components", "esm", "cjs", "umd"}
        assert mod.LOOKUP_SKIPPED_FOLDERS == (set(mod.EXCLUDED_DIR_NAMES) | mod._VENDORED_SEGMENTS
                                              | mod.TEST_FOLDERS | mod.PY_NON_CORE_TOPS | mod.LOOKUP_EXTRA_FOLDERS)
        assert "lib" not in mod.LOOKUP_SKIPPED_FOLDERS
        assert mod._lookup_skips_file("bundle.min.js") and not mod._lookup_skips_file("admin.js")


# --------------------------------------------------------------------------
# kind-at
# --------------------------------------------------------------------------

EXTRACTION_PATTERNS = (
    REPO_ROOT / "src" / "skf-create-skill" / "references" / "extraction-patterns.md"
)
FUNCTION_RECIPE = {
    "id": "py-fn", "language": "python",
    "rule": {"kind": "function_definition", "has": {"field": "name", "pattern": "$NAME"}},
}
NAME_RECIPE = {
    "id": "py-name", "language": "python",
    "rule": {"kind": "identifier", "pattern": "$NAME",
             "inside": {"kind": "function_definition", "field": "name"}},
}


def _kind_at(tmp_path: Path, capsys, rel: str, text: str, line: int,
             *flags: str, recipes: Path = EXTRACTION_PATTERNS) -> tuple[int, dict]:
    src = tmp_path / "src"
    _write_text(src, rel, text)
    return _main_json(capsys, "kind-at", "--source-root", str(src), "--file", rel,
                      "--line", str(line), "--recipes", str(recipes), *flags)


class TestLoadRecipes:
    def test_markdown_fences(self) -> None:
        recipes = mod.load_recipes(EXTRACTION_PATTERNS)
        kinds = {(r["id"], r["language"]): r["rule"]["kind"] for r in recipes}
        assert kinds[("python-public-functions", "python")] == "function_definition"
        assert kinds[("js-reexports", "typescript")] == "export_specifier"
        assert kinds[("js-exported-functions", "javascript")] == "export_statement"

    def test_templates_and_duplicates_are_skipped(self, tmp_path: Path) -> None:
        md = _write_text(tmp_path, "r.md", (
            "```yaml\nid: {recipe_id}\nlanguage: {lang}\n```\n\n"
            "```yaml\nnot: [valid\n```\n\n"
            "```yaml\nid: a\nlanguage: python\nrule:\n  kind: function_definition\n```\n\n"
            "```yaml\nid: a\nlanguage: python\nrule:\n  kind: class_definition\n```\n\n"
            "```yaml\nid: b\nlanguage: python\nrule:\n  pattern: $NAME\n```\n"))
        assert [(r["id"], r["rule"]["kind"]) for r in mod.load_recipes(md)] == [
            ("a", "function_definition")]

    def test_yaml_file_shapes(self, tmp_path: Path) -> None:
        import yaml

        docs = _write_text(tmp_path, "docs.yaml", yaml.safe_dump(FUNCTION_RECIPE)
                           + "---\n" + yaml.safe_dump(NAME_RECIPE))
        listed = _write_text(tmp_path, "list.yaml", yaml.safe_dump([FUNCTION_RECIPE, NAME_RECIPE]))
        keyed = _write_text(tmp_path, "keyed.yaml",
                            yaml.safe_dump({"recipes": [FUNCTION_RECIPE, NAME_RECIPE]}))
        for path in (docs, listed, keyed):
            assert [r["id"] for r in mod.load_recipes(path)] == ["py-fn", "py-name"], path

    def test_malformed_yaml_file_raises(self, tmp_path: Path) -> None:
        bad = _write_text(tmp_path, "bad.yaml", "id: [\n")
        with pytest.raises(ValueError):
            mod.load_recipes(bad)

    def test_language_forms(self) -> None:
        recipes = [
            {"id": "x", "language": "typescript", "rule": {"kind": "k1"}},
            {"id": "x", "language": "javascript", "rule": {"kind": "k2"}},
            {"id": "y", "language": "tsx", "rule": {"kind": "k3"}},
            {"id": "z", "language": "python", "rule": {"kind": "k4"}},
        ]

        def runs(language: str) -> list[tuple[str, str, bool]]:
            return [(r["id"], r["rule"]["kind"], r["_rewritten"])
                    for r in mod.recipe_runs(recipes, language)]

        assert runs("typescript") == [("x", "k1", False), ("y", "k3", True)]
        assert runs("tsx") == [("x", "k1", True), ("y", "k3", False)]
        assert runs("javascript") == [("x", "k2", False), ("y", "k3", True)]
        assert runs("python") == [("z", "k4", False)]
        assert runs("rust") == []
        assert all(r["language"] == "tsx" for r in mod.recipe_runs(recipes, "tsx"))


@pytest.mark.skipif(AST_GREP is None, reason="no ast-grep of the version package.json pins on PATH")
class TestKindAtRealAstGrep:
    def test_python(self, tmp_path: Path, capsys) -> None:
        text = "def search():\n    pass\n\n\nclass Client:\n    pass\n"
        code, out = _kind_at(tmp_path, capsys, "api.py", text, 1)
        assert code == 0
        assert out == {"file": "api.py", "language": "python", "line": 1, "name": None,
                       "status": "found", "kind": "function_definition",
                       "matches": [{"recipe": "python-public-functions",
                                    "kind": "function_definition", "name": "search"}],
                       "errors": []}
        _, out = _kind_at(tmp_path, capsys, "api.py", text, 5, "--name", "Client")
        assert (out["status"], out["kind"]) == ("found", "class_definition")

    def test_typescript_tsx_and_javascript(self, tmp_path: Path, capsys) -> None:
        ts = ("export const a1 = 1, B2 = () => 2;\n"
              "export { a, b as c } from './x';\n"
              "export interface ButtonProps { label: string }\n")
        _, out = _kind_at(tmp_path, capsys, "m.ts", ts, 1, "--name", "B2")
        assert (out["status"], out["kind"]) == ("found", "export_statement")
        assert [m["recipe"] for m in out["matches"]] == [
            "js-exported-arrow-functions", "react-component-arrow-functions"]
        _, out = _kind_at(tmp_path, capsys, "m.ts", ts, 2, "--name", "c")
        assert (out["status"], out["kind"]) == ("found", "export_specifier")
        _, out = _kind_at(tmp_path, capsys, "m.ts", ts, 3, "--name", "ButtonProps")
        assert out["matches"][0]["recipe"] == "react-props-interfaces"
        # tsx runs the typescript forms
        _, out = _kind_at(tmp_path, capsys, "c.tsx",
                          "export function Card() { return <div />; }\n", 1)
        assert out["language"] == "tsx"
        assert {m["recipe"] for m in out["matches"]} == {
            "js-exported-functions", "react-component-functions"}
        # javascript: its own forms, TypeScript-only recipes skipped quietly
        _, out = _kind_at(tmp_path, capsys, "a.js",
                          "export const A = () => 1;\nexport function f() {}\n", 2)
        assert (out["status"], out["kind"], out["errors"]) == ("found", "export_statement", [])

    def test_prettier_layout(self, tmp_path: Path, capsys) -> None:
        # the recipes cite a later declarator's own line, the line the
        # definition-line rules give
        _, out = _kind_at(tmp_path, capsys, "p.ts", PRETTIER_TS, 2, "--name", "B2")
        assert (out["status"], out["kind"]) == ("found", "export_statement")
        assert mod.find_definition_lines("p.ts", "B2", tmp_path / "src") == [2]

    def test_rust_and_go(self, tmp_path: Path, capsys) -> None:
        _, out = _kind_at(tmp_path, capsys, "lib.rs", "pub fn add() {}\n", 1)
        assert (out["status"], out["kind"]) == ("found", "function_item")
        _, out = _kind_at(tmp_path, capsys, "main.go",
                          "package main\n\nfunc Exported() {}\n", 3)
        assert (out["status"], out["kind"]) == ("found", "function_declaration")

    def test_name_filter_and_no_match(self, tmp_path: Path, capsys) -> None:
        text = "export const a = 1, B = () => 2;\n\n"
        _, out = _kind_at(tmp_path, capsys, "m.ts", text, 1, "--name", "a")
        assert [m["recipe"] for m in out["matches"]] == ["js-exported-constants"]
        code, out = _kind_at(tmp_path, capsys, "m.ts", text, 1, "--name", "Z")
        assert (code, out["status"], out["kind"]) == (1, "no-match", None)
        code, out = _kind_at(tmp_path, capsys, "m.ts", text, 2)
        assert (code, out["status"]) == (1, "no-match")

    def test_ambiguous(self, tmp_path: Path, capsys) -> None:
        import yaml

        recipes = _write_text(tmp_path, "r.yaml", yaml.safe_dump([FUNCTION_RECIPE, NAME_RECIPE]))
        code, out = _kind_at(tmp_path, capsys, "a.py", "def run():\n    pass\n", 1,
                             recipes=recipes)
        assert code == 1
        assert (out["status"], out["kind"]) == ("ambiguous", None)
        assert [(m["recipe"], m["kind"]) for m in out["matches"]] == [
            ("py-fn", "function_definition"), ("py-name", "identifier")]

    def test_a_recipe_ast_grep_rejects_makes_it_incomplete(self, tmp_path: Path, capsys) -> None:
        import yaml

        bad = dict(FUNCTION_RECIPE, id="bad",
                   rule={"kind": "async_function_definition"})
        recipes = _write_text(tmp_path, "r.yaml", yaml.safe_dump([FUNCTION_RECIPE, bad]))
        code, out = _kind_at(tmp_path, capsys, "a.py", "def run():\n    pass\n", 1,
                             recipes=recipes)
        assert code == 1
        assert (out["status"], out["kind"]) == ("incomplete", None)
        assert [m["recipe"] for m in out["matches"]] == ["py-fn"]
        assert [(e["recipe"], e["reason"]) for e in out["errors"]] == [
            ("bad", mod.UNCHECKED_AST_GREP_ERROR)]

    def test_skips(self, tmp_path: Path, capsys) -> None:
        code, out = _kind_at(tmp_path, capsys, "notes.txt", "def run(): pass\n", 1)
        assert (code, out["status"], out["language"]) == (1, "skipped-no-language", None)
        _, out = _kind_at(tmp_path, capsys, "notes.txt", "def run(): pass\n", 1,
                          "--language", "Python")
        assert (out["status"], out["kind"]) == ("found", "function_definition")
        _, out = _kind_at(tmp_path, capsys, "a.rb", "def run; end\n", 1)
        assert out["status"] == "skipped-no-recipes"

    def test_many_targets_in_one_file(self, tmp_path: Path) -> None:
        recipes = mod.load_recipes(EXTRACTION_PATTERNS)
        source = b"def a():\n    pass\n\nclass B:\n    pass\n"
        results = mod.kinds_at(source, "python", [(1, "a"), (4, None), (2, None)], recipes)
        assert [(r["status"], r["kind"]) for r in results] == [
            ("found", "function_definition"), ("found", "class_definition"),
            ("no-match", None)]


class FakeScan:
    """`subprocess.run` stand-in for kind-at: records each call and its rule
    file, answers with `answer` (a result, or an exception to raise)."""

    def __init__(self, answer: object) -> None:
        self.answer = answer
        self.calls: list[list[str]] = []
        self.rules: list[dict] = []

    def __call__(self, cmd: list[str], **kwargs: object) -> SimpleNamespace:
        self.calls.append(list(cmd))
        rule = Path(cmd[cmd.index("-r") + 1])
        self.rules.append(json.loads(rule.read_text(encoding="utf-8")))
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer


class TestKindAtWithoutAstGrep:
    RECIPES = [dict(FUNCTION_RECIPE), dict(NAME_RECIPE, id="second")]

    def test_no_ast_grep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod.shutil, "which", lambda name: None)
        fake = FakeScan(AssertionError("ast-grep was run"))
        monkeypatch.setattr(mod.subprocess, "run", fake)
        (result,) = mod.kinds_at(b"def a(): pass\n", "python", [(1, None)], self.RECIPES)
        assert result["status"] == "skipped-no-ast-grep" and fake.calls == []

    def test_the_rule_goes_in_a_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _which_ast_grep(monkeypatch)
        line = json.dumps({"metaVariables": {"single": {"NAME": {
            "text": "a", "range": {"start": {"line": 0}}}}}})
        fake = FakeScan(SimpleNamespace(returncode=0, stdout=(line + "\n").encode(), stderr=b""))
        monkeypatch.setattr(mod.subprocess, "run", fake)
        recipes = [{"id": "t", "language": "typescript",
                    "rule": {"kind": "export_statement", "regex": "^[^_]|x"}}]
        (result,) = mod.kinds_at(b"export const a = 1;\n", "tsx", [(1, "a")], recipes)
        assert (result["status"], result["kind"]) == ("found", "export_statement")
        (cmd,) = fake.calls
        assert cmd[1:3] == ["scan", "--config"] and "--stdin" in cmd
        assert "--json=stream" in cmd and "--inline-rules" not in cmd
        assert fake.rules == [{"id": "t", "language": "tsx",
                               "rule": {"kind": "export_statement", "regex": "^[^_]|x"}}]

    def test_first_timeout_ends_the_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _which_ast_grep(monkeypatch)
        fake = FakeScan(subprocess.TimeoutExpired(["ast-grep"], 30))
        monkeypatch.setattr(mod.subprocess, "run", fake)
        (result,) = mod.kinds_at(b"def a(): pass\n", "python", [(1, None)], self.RECIPES)
        assert result["status"] == "incomplete" and result["kind"] is None
        assert len(fake.calls) == 1
        assert [(e["recipe"], e["reason"]) for e in result["errors"]] == [
            ("py-fn", mod.UNCHECKED_TIMEOUT), ("second", mod.UNCHECKED_TIMEOUT)]

    def test_unreadable_output_is_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _which_ast_grep(monkeypatch)
        fake = FakeScan(SimpleNamespace(returncode=0, stdout=b"not json\n", stderr=b""))
        monkeypatch.setattr(mod.subprocess, "run", fake)
        (result,) = mod.kinds_at(b"def a(): pass\n", "python", [(1, None)], self.RECIPES)
        assert result["status"] == "incomplete"
        assert {e["reason"] for e in result["errors"]} == {mod.UNCHECKED_AST_GREP_ERROR}

    def test_a_backslash_path_resolves(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        # a source_file as an entry may record it, read as verify reads it
        monkeypatch.setattr(mod.shutil, "which", lambda name: None)
        src = tmp_path / "src"
        _write_text(src, "lib/a.py", "def a(): pass\n")
        code, out = _main_json(capsys, "kind-at", "--source-root", str(src),
                               "--file", "lib\\a.py", "--line", "1",
                               "--recipes", str(EXTRACTION_PATTERNS))
        assert (code, out["file"], out["language"], out["status"]) == (
            1, "lib\\a.py", "python", "skipped-no-ast-grep")

    def test_input_errors_exit_2(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        _write_text(src, "a.py", "def a(): pass\n")
        empty = _write_text(tmp_path, "empty.md", "# no recipes\n")
        cases = [
            (["--file", "gone.py", "--recipes", str(EXTRACTION_PATTERNS)], "source file not found"),
            (["--file", "a.py", "--recipes", str(tmp_path / "gone.md")], "recipes not found"),
            (["--file", "a.py", "--recipes", str(empty)], "no ast-grep recipe"),
        ]
        for args, message in cases:
            result = _run_cli("kind-at", "--source-root", str(src), "--line", "1", *args)
            assert result.returncode == 2, args
            assert result.stdout == "" and message in result.stderr


# --------------------------------------------------------------------------
# fix: a byte-for-byte fixture (#584)
# --------------------------------------------------------------------------

UTIL_TS = "export const WIDTH = 1;\n\nexport function size() {}\n"
FIX_SKILL_MD = """\
# demo

`LIMIT` caps results [AST:src/lib/config.py:L6] and `DEFAULT` sets the page [AST:./src/lib/config.py:L7].
Both at once [AST:src/lib/config.py:L6-L7] and [SRC:src\\lib\\config.py:L6-9].
`search` [AST:src/lib/config.py:L11] finds.
`size` [AST:src/lib/util.ts:L1] shares a line with `WIDTH`.

<!-- [MANUAL:notes] -->
Keep: [AST:src/lib/config.py:L6] and [AST:src/lib/config.py:L11].
<!-- [/MANUAL:notes] -->
"""
FIX_API_MD = """\
## API

- `LIMIT` [AST:src/lib/config.py:L6]
- `DEFAULT` [AST:src/lib/config.py:L7]
- `search` [AST:src/lib/config.py:L11]
"""
FIX_ENTRIES = [
    {"export_name": "LIMIT", "source_file": "src/lib/config.py", "source_line": 6,
     "extraction_method": "ast-grep"},
    {"export_name": "DEFAULT", "source_file": "src/lib/config.py", "source_line": 7,
     "extraction_method": "ast-grep"},
    {"export_name": "search", "source_file": "src/lib/config.py", "source_line": 11,
     "extraction_method": "source-read"},
    {"export_name": "WIDTH", "source_file": "src/lib/util.ts", "source_line": 1,
     "extraction_method": "ast-grep"},
    {"export_name": "size", "source_file": "src/lib/util.ts", "source_line": 1,
     "extraction_method": "ast-grep"},
]
# LIMIT moves 6 -> 7 and DEFAULT 7 -> 8 in one pass: a citation of line 6
# goes to 7 and stops there. search's [AST:] becomes [SRC:]. The util.ts
# line 1 citation stays (WIDTH records that line too), and nothing inside
# the [MANUAL] block changes.
FIXED_SKILL_MD = """\
# demo

`LIMIT` caps results [AST:src/lib/config.py:L7] and `DEFAULT` sets the page [AST:./src/lib/config.py:L8].
Both at once [AST:src/lib/config.py:L7-L8] and [AST:src\\lib\\config.py:L7-10].
`search` [SRC:src/lib/config.py:L11] finds.
`size` [AST:src/lib/util.ts:L1] shares a line with `WIDTH`.

<!-- [MANUAL:notes] -->
Keep: [AST:src/lib/config.py:L6] and [AST:src/lib/config.py:L11].
<!-- [/MANUAL:notes] -->
"""
FIXED_API_MD = """\
## API

- `LIMIT` [AST:src/lib/config.py:L7]
- `DEFAULT` [AST:src/lib/config.py:L8]
- `search` [SRC:src/lib/config.py:L11]
"""
FIXED_PROVENANCE = """\
{
  "source_root": "unused",
  "entries": [
    {
      "export_name": "LIMIT",
      "source_file": "src/lib/config.py",
      "source_line": 7,
      "extraction_method": "ast-grep"
    },
    {
      "export_name": "DEFAULT",
      "source_file": "src/lib/config.py",
      "source_line": 8,
      "extraction_method": "ast-grep"
    },
    {
      "export_name": "search",
      "source_file": "src/lib/config.py",
      "source_line": 11,
      "extraction_method": "source-read"
    },
    {
      "export_name": "WIDTH",
      "source_file": "src/lib/util.ts",
      "source_line": 1,
      "extraction_method": "ast-grep"
    },
    {
      "export_name": "size",
      "source_file": "src/lib/util.ts",
      "source_line": 3,
      "extraction_method": "ast-grep"
    }
  ]
}
"""
HASH_CONTENT = REPO_ROOT / "src" / "shared" / "scripts" / "skf-hash-content.py"


def _write_bytes(root: Path, rel: str, text: str) -> Path:
    """Write text as UTF-8 bytes, so LF line ends stay LF on Windows too."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))
    return p


class FixPackage(NamedTuple):
    root: Path
    skill: Path
    prov: Path
    meta: Path


def _fix_package(tmp_path: Path, skill_md: str = FIX_SKILL_MD, api_md: str = FIX_API_MD,
                 entries: list | None = None) -> FixPackage:
    root = tmp_path / "source"
    _write_bytes(root, "src/lib/config.py", PY_CONFIG)
    _write_bytes(root, "src/lib/util.ts", UTIL_TS)
    skill = tmp_path / "skill"
    _write_bytes(skill, "SKILL.md", skill_md)
    _write_bytes(skill, "references/api.md", api_md)
    entries = copy.deepcopy(FIX_ENTRIES if entries is None else entries)
    names = [e["export_name"] for e in entries]
    meta = _write_json(skill / "metadata.json", {"exports": names})
    prov = _write_json(skill / "provenance-map.json", {"source_root": "unused", "entries": entries})
    return FixPackage(root, skill, prov, meta)


def _verify_to_file(pkg: FixPackage, out: Path) -> dict:
    result = _run_cli("verify", "--metadata", str(pkg.meta), "--provenance", str(pkg.prov),
                      "--source-root", str(pkg.root), "--skill-dir", str(pkg.skill), "-o", str(out))
    assert result.returncode in (0, 1), result.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def _fix(pkg: FixPackage, verify_json: Path, *flags: str) -> tuple[int, dict]:
    result = _run_cli("fix", "--verify", str(verify_json), "--provenance", str(pkg.prov),
                      "--skill-dir", str(pkg.skill), *flags)
    assert result.returncode in (0, 1), result.stderr
    return result.returncode, json.loads(result.stdout)


def _manual_inventory(skill: Path, out: Path) -> Path:
    result = subprocess.run([sys.executable, str(HASH_CONTENT), "manual-inventory",
                             str(skill / "SKILL.md")], capture_output=True, check=True)
    out.write_bytes(result.stdout)
    return out


class TestFixByteForByte:
    def test_fixture(self, tmp_path: Path) -> None:
        pkg = _fix_package(tmp_path)
        verify_json = tmp_path / "verify.json"
        _verify_to_file(pkg, verify_json)
        inventory = _manual_inventory(pkg.skill, tmp_path / "inventory.json")
        code, out = _fix(pkg, verify_json, "--manual-inventory", str(inventory))

        assert (pkg.skill / "SKILL.md").read_bytes() == FIXED_SKILL_MD.encode("utf-8")
        assert (pkg.skill / "references" / "api.md").read_bytes() == FIXED_API_MD.encode("utf-8")
        assert pkg.prov.read_bytes() == FIXED_PROVENANCE.encode("utf-8")

        assert code == 1  # the [MANUAL] and shared-line citations are left
        assert out["applied"] == [
            {"kind": "citation-prefix", "file": "SKILL.md", "line": 4,
             "citation": "[SRC:src\\lib\\config.py:L6-9]",
             "fixed": "[AST:src\\lib\\config.py:L7-10]"},
            {"kind": "citation-prefix", "file": "SKILL.md", "line": 5,
             "citation": "[AST:src/lib/config.py:L11]",
             "fixed": "[SRC:src/lib/config.py:L11]"},
            {"kind": "citation-prefix", "file": "references/api.md", "line": 5,
             "citation": "[AST:src/lib/config.py:L11]",
             "fixed": "[SRC:src/lib/config.py:L11]"},
            {"kind": "source-line", "entry_index": 0, "export_name": "LIMIT",
             "source_file": "src/lib/config.py", "from": 6, "to": 7},
            {"kind": "source-line", "entry_index": 1, "export_name": "DEFAULT",
             "source_file": "src/lib/config.py", "from": 7, "to": 8},
            {"kind": "source-line", "entry_index": 4, "export_name": "size",
             "source_file": "src/lib/util.ts", "from": 1, "to": 3},
            {"kind": "citation-line", "file": "SKILL.md", "line": 3,
             "citation": "[AST:src/lib/config.py:L6]",
             "fixed": "[AST:src/lib/config.py:L7]", "export_names": ["LIMIT"]},
            {"kind": "citation-line", "file": "SKILL.md", "line": 3,
             "citation": "[AST:./src/lib/config.py:L7]",
             "fixed": "[AST:./src/lib/config.py:L8]", "export_names": ["DEFAULT"]},
            {"kind": "citation-line", "file": "SKILL.md", "line": 4,
             "citation": "[AST:src/lib/config.py:L6-L7]",
             "fixed": "[AST:src/lib/config.py:L7-L8]", "export_names": ["LIMIT"]},
            {"kind": "citation-line", "file": "SKILL.md", "line": 4,
             "citation": "[SRC:src\\lib\\config.py:L6-9]",
             "fixed": "[AST:src\\lib\\config.py:L7-10]", "export_names": ["LIMIT"]},
            {"kind": "citation-line", "file": "references/api.md", "line": 3,
             "citation": "[AST:src/lib/config.py:L6]",
             "fixed": "[AST:src/lib/config.py:L7]", "export_names": ["LIMIT"]},
            {"kind": "citation-line", "file": "references/api.md", "line": 4,
             "citation": "[AST:src/lib/config.py:L7]",
             "fixed": "[AST:src/lib/config.py:L8]", "export_names": ["DEFAULT"]},
        ]
        assert [(w["kind"], w["file"], w["line"], w["citation"], w["why"])
                for w in out["left_as_warn"]] == [
            ("citation-prefix", "SKILL.md", 9, "[AST:src/lib/config.py:L11]",
             "inside-manual-block"),
            ("citation-line", "SKILL.md", 6, "[AST:src/lib/util.ts:L1]", "shared-line"),
            ("citation-line", "SKILL.md", 9, "[AST:src/lib/config.py:L6]",
             "inside-manual-block"),
        ]
        assert out["left_as_warn"][1]["export_names"] == ["WIDTH", "size"]
        expected_files = [str(pkg.skill / "SKILL.md"), str(pkg.skill / "references" / "api.md"),
                          str(pkg.prov)]
        assert out["files_changed"] == expected_files
        assert out["files_written"] == expected_files
        assert out["dry_run"] is False
        assert out["manual_verify"]["ok"] is True
        assert out["manual_verify"]["preserved"] == ["notes"]
        assert out["summary"] == {"citation_prefixes_fixed": 3, "source_lines_moved": 3,
                                  "citations_moved": 6, "left_as_warn_count": 3}

    def test_verify_again_leaves_only_the_manual_citation(self, tmp_path: Path) -> None:
        pkg = _fix_package(tmp_path)
        verify_json = tmp_path / "verify.json"
        _verify_to_file(pkg, verify_json)
        _fix(pkg, verify_json)
        again = _verify_to_file(pkg, tmp_path / "again.json")
        assert again["stale"] == []
        assert [(c["file"], c["line"], c["citation"]) for c in again["citations"]] == [
            ("SKILL.md", 9, "[AST:src/lib/config.py:L11]")]
        # and a second fix changes nothing
        code, out = _fix(pkg, tmp_path / "again.json")
        assert out["applied"] == [] and out["files_written"] == []
        assert pkg.prov.read_bytes() == FIXED_PROVENANCE.encode("utf-8")

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        pkg = _fix_package(tmp_path)
        verify_json = tmp_path / "verify.json"
        _verify_to_file(pkg, verify_json)
        before = {p: p.read_bytes() for p in (pkg.skill / "SKILL.md", pkg.prov)}
        _, out = _fix(pkg, verify_json, "--dry-run")
        assert {p: p.read_bytes() for p in before} == before
        assert out["dry_run"] is True and out["files_written"] == []
        assert len(out["files_changed"]) == 3
        assert out["summary"]["source_lines_moved"] == 3

    def test_no_line_moves(self, tmp_path: Path) -> None:
        pkg = _fix_package(tmp_path)
        verify_json = tmp_path / "verify.json"
        _verify_to_file(pkg, verify_json)
        _, out = _fix(pkg, verify_json, "--no-line-moves")
        assert out["summary"]["source_lines_moved"] == 0
        assert out["summary"]["citations_moved"] == 0
        assert out["summary"]["citation_prefixes_fixed"] == 3
        assert sorted(w["export_name"] for w in out["left_as_warn"]
                      if w["why"] == "line-moves-skipped") == ["DEFAULT", "LIMIT", "size"]
        assert json.loads(pkg.prov.read_text(encoding="utf-8"))["entries"] == FIX_ENTRIES


def _fix_json(tmp_path: Path, verify_result: dict) -> Path:
    return _write_json(tmp_path / "verify.json", verify_result)


def _stale(name: str, source_file: str, line: int, defs: list[int], **extra: object) -> dict:
    return dict({"export_name": name, "source_file": source_file, "source_line": line,
                 "reason": mod.STALE_LINE_NOT_DEFINITION, "definition_lines": defs}, **extra)


class TestFixPlan:
    def test_findings_nobody_can_decide_alone_are_left(self, tmp_path: Path) -> None:
        pkg = _fix_package(tmp_path, skill_md="# s\n", api_md="")
        verify_json = _fix_json(tmp_path, {"stale": [
            _stale("LIMIT", "src/lib/config.py", 6, []),
            _stale("DEFAULT", "src/lib/config.py", 7, [8, 9]),
            {"export_name": "search", "source_file": "gone.py", "source_line": 1,
             "reason": mod.STALE_FILE_MISSING},
            _stale("size", "src/lib/util.ts", 1, [0]),
            _stale("nobody", "src/lib/util.ts", 1, [3]),
        ], "citations": []})
        code, out = _fix(pkg, verify_json)
        assert code == 1 and out["applied"] == []
        assert [(w["export_name"], w["why"]) for w in out["left_as_warn"]] == [
            ("LIMIT", "no-definition-line"), ("DEFAULT", "several-definition-lines"),
            ("search", "needs-decision"), ("size", "needs-decision"),
            ("nobody", "entry-not-found")]
        assert out["files_written"] == []

    def test_entry_index_falls_back_to_name_file_and_line(self, tmp_path: Path) -> None:
        entries = copy.deepcopy(FIX_ENTRIES)
        entries.insert(0, {"export_name": "extra", "source_file": "x.py", "source_line": 1})
        pkg = _fix_package(tmp_path, skill_md="# s\n", api_md="", entries=entries)
        # a stale entry_index (the map gained an entry since) and none at all
        verify_json = _fix_json(tmp_path, {"stale": [
            _stale("LIMIT", "src/lib/config.py", 6, [7], entry_index=0),
            _stale("DEFAULT", "src/lib/config.py", 7, [8]),
        ], "citations": []})
        _, out = _fix(pkg, verify_json)
        assert [(a["entry_index"], a["export_name"]) for a in out["applied"]] == [
            (1, "LIMIT"), (2, "DEFAULT")]

    def test_entries_moving_together_take_the_citation(self, tmp_path: Path) -> None:
        # two entries on one line: moving to the same line, the citation
        # follows; moving apart, it may cite either, so it stays
        entries = [
            {"export_name": "LIMIT", "source_file": "src/lib/config.py", "source_line": 6},
            {"export_name": "LIMIT", "source_file": "src/lib/config.py", "source_line": 6},
            {"export_name": "DEFAULT", "source_file": "src/lib/config.py", "source_line": 5},
            {"export_name": "search", "source_file": "src/lib/config.py", "source_line": 5},
        ]
        pkg = _fix_package(tmp_path, skill_md="a [SRC:src/lib/config.py:L6] b [SRC:src/lib/config.py:L5]\n",
                           api_md="", entries=entries)
        verify_json = _fix_json(tmp_path, {"stale": [
            _stale("LIMIT", "src/lib/config.py", 6, [7], entry_index=0),
            _stale("LIMIT", "src/lib/config.py", 6, [7], entry_index=1),
            _stale("DEFAULT", "src/lib/config.py", 5, [8], entry_index=2),
            _stale("search", "src/lib/config.py", 5, [11], entry_index=3),
        ], "citations": []})
        _, out = _fix(pkg, verify_json)
        assert (pkg.skill / "SKILL.md").read_text(encoding="utf-8") == (
            "a [SRC:src/lib/config.py:L7] b [SRC:src/lib/config.py:L5]\n")
        (left,) = out["left_as_warn"]
        assert (left["why"], left["export_names"]) == ("shared-line", ["DEFAULT", "search"])

    def test_prefix_fix_needs_the_citation_on_its_line(self, tmp_path: Path) -> None:
        pkg = _fix_package(tmp_path, skill_md="x\n[AST:src/lib/config.py:L11]\n", api_md="")
        verify_json = _fix_json(tmp_path, {"stale": [], "citations": [
            {"file": "SKILL.md", "line": 1, "citation": "[AST:src/lib/config.py:L11]",
             "expected_prefix": "SRC"},
            {"file": "../outside.md", "line": 1, "citation": "[AST:a:L1]",
             "expected_prefix": "SRC"},
            {"file": "SKILL.md", "line": "2", "citation": "[AST:src/lib/config.py:L11]",
             "expected_prefix": "SRC"},
        ]})
        code, out = _fix(pkg, verify_json)
        assert code == 1 and out["applied"] == []
        assert [w["why"] for w in out["left_as_warn"]] == ["citation-not-found"] * 3
        assert (pkg.skill / "SKILL.md").read_text(encoding="utf-8") == (
            "x\n[AST:src/lib/config.py:L11]\n")

    def test_line_ends_bom_and_other_bytes_survive(self, tmp_path: Path) -> None:
        pkg = _fix_package(tmp_path, skill_md="# s\n", api_md="")
        raw = ("\ufeffone [AST:src/lib/config.py:L6]\r\n"
               "two\rthree [AST:src/lib/config.py:L6-8]\n").encode("utf-8") + b"\xff\xfe end\r\n"
        (pkg.skill / "SKILL.md").write_bytes(raw)
        verify_json = _fix_json(tmp_path, {"stale": [
            _stale("LIMIT", "src/lib/config.py", 6, [7], entry_index=0)], "citations": []})
        code, out = _fix(pkg, verify_json)
        assert code == 0 and out["left_as_warn"] == []
        assert (pkg.skill / "SKILL.md").read_bytes() == raw.replace(b"L6]", b"L7]").replace(
            b"L6-8]", b"L7-9]")
        assert [a["line"] for a in out["applied"] if a["kind"] == "citation-line"] == [1, 3]

    def test_writes_go_through_the_atomic_helper(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        pkg = _fix_package(tmp_path)
        verify_json = tmp_path / "verify.json"
        _verify_to_file(pkg, verify_json)
        real_run = subprocess.run
        targets: list[str] = []

        def spy(cmd: list[str], **kwargs: object):
            assert Path(cmd[1]).name == "skf-atomic-write.py" and cmd[2] == "write"
            targets.append(cmd[cmd.index("--target") + 1])
            return real_run(cmd, **kwargs)

        monkeypatch.setattr(mod.subprocess, "run", spy)
        code = mod.main(["fix", "--verify", str(verify_json), "--provenance", str(pkg.prov),
                         "--skill-dir", str(pkg.skill)])
        assert code == 1
        assert targets == [str(pkg.skill / "SKILL.md"), str(pkg.skill / "references" / "api.md"),
                           str(pkg.prov)]
        assert json.loads(capsys.readouterr().out)["files_written"] == targets
        assert not list(pkg.skill.rglob("*.skf-tmp"))

    def test_no_atomic_helper_writes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        pkg = _fix_package(tmp_path)
        verify_json = tmp_path / "verify.json"
        _verify_to_file(pkg, verify_json)
        before = pkg.prov.read_bytes()
        monkeypatch.setattr(mod, "_sibling_helper", lambda filename: None)
        code = mod.main(["fix", "--verify", str(verify_json), "--provenance", str(pkg.prov),
                         "--skill-dir", str(pkg.skill)])
        captured = capsys.readouterr()
        assert code == 2 and captured.out == ""
        assert "skf-atomic-write.py not found" in captured.err
        assert pkg.prov.read_bytes() == before
        assert (pkg.skill / "SKILL.md").read_bytes() == FIX_SKILL_MD.encode("utf-8")

    def test_a_failed_write_names_what_was_written(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        pkg = _fix_package(tmp_path)
        verify_json = tmp_path / "verify.json"
        _verify_to_file(pkg, verify_json)
        calls: list[str] = []

        def fail_second(helper: Path, target: Path, data: bytes) -> None:
            calls.append(str(target))
            if len(calls) == 2:
                raise OSError(f"atomic write of {target} failed: disk full")
            target.write_bytes(data)

        monkeypatch.setattr(mod, "atomic_write", fail_second)
        code = mod.main(["fix", "--verify", str(verify_json), "--provenance", str(pkg.prov),
                         "--skill-dir", str(pkg.skill)])
        captured = capsys.readouterr()
        assert code == 2 and captured.out == ""
        assert "disk full" in captured.err
        assert f"already written: {pkg.skill / 'SKILL.md'}" in captured.err

    def test_manual_verify_catches_a_changed_block(self, tmp_path: Path) -> None:
        pkg = _fix_package(tmp_path)
        verify_json = tmp_path / "verify.json"
        _verify_to_file(pkg, verify_json)
        inventory = _manual_inventory(pkg.skill, tmp_path / "inventory.json")
        data = json.loads(inventory.read_text(encoding="utf-8"))
        data["blocks"][0]["content_hash"] = "sha256:" + "0" * 64
        inventory.write_text(json.dumps(data), encoding="utf-8")
        code, out = _fix(pkg, verify_json, "--manual-inventory", str(inventory))
        assert code == 1
        assert out["manual_verify"]["ok"] is False
        assert out["manual_verify"]["modified"] == ["notes"]

    def test_a_failed_manual_recheck_exits_2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        # after the writes: exit 2 naming what was written, never exit 1
        # (read as something left as a WARN)
        pkg = _fix_package(tmp_path)
        verify_json = tmp_path / "verify.json"
        _verify_to_file(pkg, verify_json)
        inventory = _manual_inventory(pkg.skill, tmp_path / "inventory.json")
        real_load = mod._load_sibling_module

        def load(filename: str, module_name: str):
            module = real_load(filename, module_name)

            def unreadable(data: bytes) -> list:
                raise OSError("SKILL.md vanished")

            module.find_manual_blocks = unreadable
            return module

        monkeypatch.setattr(mod, "_load_sibling_module", load)
        code = mod.main(["fix", "--verify", str(verify_json), "--provenance", str(pkg.prov),
                         "--skill-dir", str(pkg.skill), "--manual-inventory", str(inventory)])
        out, err = capsys.readouterr()
        assert (code, out) == (2, "")
        assert err.startswith(
            "error: the [MANUAL] re-check failed: OSError: SKILL.md vanished; "
            f"already written: {pkg.skill / 'SKILL.md'}, ")
        assert err.rstrip("\n").endswith(str(pkg.prov)) and err.count("\n") == 1

    def test_an_unwritable_result_exits_2(self, tmp_path: Path) -> None:
        pkg = _fix_package(tmp_path)
        verify_json = tmp_path / "verify.json"
        _verify_to_file(pkg, verify_json)
        gone = str(tmp_path / "gone" / "out.json")
        result = _run_cli("fix", "--verify", str(verify_json), "--provenance", str(pkg.prov),
                          "--skill-dir", str(pkg.skill), "-o", gone)
        assert (result.returncode, result.stdout) == (2, "")
        assert result.stderr.startswith(f"error: writing {gone} failed: FileNotFoundError: ")
        assert f"; already written: {pkg.skill / 'SKILL.md'}, " in result.stderr
        assert result.stderr.count("\n") == 1

    def test_input_errors_exit_2(self, tmp_path: Path) -> None:
        pkg = _fix_package(tmp_path)
        verify_json = tmp_path / "verify.json"
        _verify_to_file(pkg, verify_json)
        not_verify = _write_json(tmp_path / "other.json", {"status": "pass"})
        bad_inventory = _write_text(tmp_path, "inv.json", "{nope")
        no_skill = tmp_path / "empty"
        no_skill.mkdir()
        before = pkg.prov.read_bytes()
        cases = [
            (["--verify", str(not_verify), "--provenance", str(pkg.prov),
              "--skill-dir", str(pkg.skill)], "is not a verify result"),
            (["--verify", str(tmp_path / "gone.json"), "--provenance", str(pkg.prov),
              "--skill-dir", str(pkg.skill)], "verify result not found"),
            (["--verify", str(verify_json), "--provenance", str(pkg.prov),
              "--skill-dir", str(no_skill)], "has no SKILL.md"),
            (["--verify", str(verify_json), "--provenance", str(pkg.prov),
              "--skill-dir", str(pkg.skill), "--manual-inventory", str(bad_inventory)],
             "failed to read inventory"),
        ]
        for args, message in cases:
            result = _run_cli("fix", *args)
            assert result.returncode == 2, args
            assert result.stdout == "" and message in result.stderr, result.stderr
        assert pkg.prov.read_bytes() == before

    def test_manual_markers_match_hash_content(self) -> None:
        spec = importlib.util.spec_from_file_location("skf_hash_content_pin", HASH_CONTENT)
        hash_content = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(hash_content)
        assert mod._MANUAL_OPEN_RE.pattern.encode() == hash_content._OPEN_RE.pattern
        assert mod._MANUAL_CLOSE_RE.pattern.encode() == hash_content._CLOSE_RE.pattern
        # `\s` as the bytes patterns read it: ASCII whitespace only
        assert mod._MANUAL_OPEN_RE.flags & re.ASCII
        assert mod._MANUAL_CLOSE_RE.flags & re.ASCII
        text = ("a <!-- [MANUAL:x] -->in<!-- [/MANUAL:y] --> <!-- [/MANUAL:x] -->"
                " <!-- [MANUAL:open] --> tail")
        (span,) = mod.manual_interiors(text)
        assert text[span[0]:span[1]] == "in<!-- [/MANUAL:y] --> "
        (block,) = hash_content.find_manual_blocks(text.encode("utf-8"))
        assert block["name"] == "x"
        # a marker spaced with U+00A0 is no marker to either
        for nbsp in ("a <!--\u00a0[MANUAL:x] -->in<!-- [/MANUAL:x] -->",
                     "a <!-- [MANUAL:x] -->in<!-- [/MANUAL:x]\u00a0-->"):
            assert mod.manual_interiors(nbsp) == []
            assert hash_content.find_manual_blocks(nbsp.encode("utf-8")) == []
