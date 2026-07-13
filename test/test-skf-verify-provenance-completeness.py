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
  - CLI smoke: exit 0 clean, exit 1 findings, exit 2 on bad input
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


def _write_source(root: Path, rel: str, lines: int) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(f"line {i}" for i in range(1, lines + 1)), encoding="utf-8")
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
        _write_source(src, "src/a.ts", 10)
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
        _write_source(src, "lib/foo.ts", 5)
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
        _write_source(src, "a.ts", 10)
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
