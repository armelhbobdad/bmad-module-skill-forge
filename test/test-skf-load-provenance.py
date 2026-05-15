#!/usr/bin/env python3
"""Tests for skf-load-provenance.py.

Covers:
  - normalize: bounded_scan_files union, dedup, POSIX, sorted
  - stack detection: v2 + libraries, v2 + skill_type=stack, v1 + libraries
    (legacy), v1 + skill_type=stack (legacy), neither (single skill)
  - reexport_map: top-level form, per-entry reexported_as form, mixed
  - source_root / baseline_commit / baseline_ref pass-through (and null when
    absent)
  - error paths: missing file, malformed JSON, non-object top-level
  - CLI smoke: exit 0 + JSON shape; exit 1 on malformed input
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-load-provenance.py"

spec = importlib.util.spec_from_file_location("skf_load_provenance", SCRIPT_PATH)
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


# --------------------------------------------------------------------------
# bounded_scan_files
# --------------------------------------------------------------------------


class TestBoundedScanFiles:
    def test_union_of_entries_and_file_entries(self) -> None:
        data = {
            "entries": [
                {"source_file": "src/auth.ts"},
                {"source_file": "src/util.ts"},
            ],
            "file_entries": [
                {"source_file": "scripts/build.sh"},
                {"source_file": "src/auth.ts"},  # duplicate across both lists
            ],
        }
        assert mod.bounded_scan_files(data) == [
            "scripts/build.sh",
            "src/auth.ts",
            "src/util.ts",
        ]

    def test_empty_map(self) -> None:
        assert mod.bounded_scan_files({}) == []

    def test_normalizes_backslashes_to_posix(self) -> None:
        data = {"entries": [{"source_file": "src\\windows\\thing.ts"}]}
        assert mod.bounded_scan_files(data) == ["src/windows/thing.ts"]

    def test_skips_non_string_source_file(self) -> None:
        data = {
            "entries": [
                {"source_file": None},
                {"source_file": 42},
                {"source_file": "valid.ts"},
                {},
            ],
        }
        assert mod.bounded_scan_files(data) == ["valid.ts"]

    def test_skips_non_dict_entries(self) -> None:
        data = {"entries": ["not an object", {"source_file": "ok.ts"}]}
        assert mod.bounded_scan_files(data) == ["ok.ts"]

    def test_entries_field_not_list_is_ignored(self) -> None:
        data = {"entries": "not a list", "file_entries": [{"source_file": "a.ts"}]}
        assert mod.bounded_scan_files(data) == ["a.ts"]


# --------------------------------------------------------------------------
# detect_stack_flags
# --------------------------------------------------------------------------


class TestDetectStackFlags:
    def test_v2_with_skill_type_stack(self) -> None:
        is_stack, legacy = mod.detect_stack_flags(
            {"provenance_version": "2.0", "skill_type": "stack"}
        )
        assert (is_stack, legacy) == (True, False)

    def test_v2_with_libraries_key(self) -> None:
        is_stack, legacy = mod.detect_stack_flags(
            {"provenance_version": "2.0", "libraries": {"lib-a": {}}}
        )
        assert (is_stack, legacy) == (True, False)

    def test_v1_with_libraries_is_legacy(self) -> None:
        is_stack, legacy = mod.detect_stack_flags(
            {"provenance_version": "1.0", "libraries": ["lib-a"]}
        )
        assert (is_stack, legacy) == (True, True)

    def test_v1_with_skill_type_stack_is_legacy(self) -> None:
        is_stack, legacy = mod.detect_stack_flags(
            {"provenance_version": "1.0", "skill_type": "stack"}
        )
        assert (is_stack, legacy) == (True, True)

    def test_unversioned_with_libraries_is_legacy(self) -> None:
        # absent provenance_version treated as v1
        is_stack, legacy = mod.detect_stack_flags({"libraries": {"x": {}}})
        assert (is_stack, legacy) == (True, True)

    def test_single_skill_not_stack(self) -> None:
        is_stack, legacy = mod.detect_stack_flags(
            {"provenance_version": "2.0", "skill_type": "single"}
        )
        assert (is_stack, legacy) == (False, False)

    def test_empty_map_not_stack(self) -> None:
        assert mod.detect_stack_flags({}) == (False, False)


# --------------------------------------------------------------------------
# extract_reexport_map
# --------------------------------------------------------------------------


class TestExtractReexportMap:
    def test_top_level_reexport_map(self) -> None:
        data = {"reexport_map": {"_Impl": "Public", "_X": "Y"}}
        assert mod.extract_reexport_map(data) == {"_Impl": "Public", "_X": "Y"}

    def test_per_entry_reexported_as(self) -> None:
        data = {
            "entries": [
                {"export_name": "_Internal", "reexported_as": "Public"},
                {"export_name": "AlsoInternal", "reexported_as": "Visible"},
                {"export_name": "NoReexport"},  # skipped
            ],
        }
        assert mod.extract_reexport_map(data) == {
            "_Internal": "Public",
            "AlsoInternal": "Visible",
        }

    def test_top_level_wins_over_per_entry_collision(self) -> None:
        data = {
            "reexport_map": {"_X": "FromTop"},
            "entries": [{"export_name": "_X", "reexported_as": "FromEntry"}],
        }
        assert mod.extract_reexport_map(data) == {"_X": "FromTop"}

    def test_empty_when_neither_form_present(self) -> None:
        assert mod.extract_reexport_map({"entries": [{"export_name": "X"}]}) == {}

    def test_non_dict_reexport_map_ignored(self) -> None:
        assert mod.extract_reexport_map({"reexport_map": "not an object"}) == {}


# --------------------------------------------------------------------------
# normalize end-to-end
# --------------------------------------------------------------------------


class TestNormalize:
    def test_single_skill_v2(self) -> None:
        data = {
            "provenance_version": "2.0",
            "source_root": "/path/to/src",
            "source_commit": "abc123",
            "source_ref": "v1.0.0",
            "entries": [{"source_file": "src/a.ts"}],
            "file_entries": [{"source_file": "scripts/b.sh"}],
        }
        result = mod.normalize(data)
        assert result == {
            "bounded_scan_files": ["scripts/b.sh", "src/a.ts"],
            "is_stack_skill": False,
            "legacy_stack_provenance": False,
            "source_root": "/path/to/src",
            "baseline_commit": "abc123",
            "baseline_ref": "v1.0.0",
            "reexport_map": {},
        }

    def test_stack_skill_v2(self) -> None:
        data = {
            "provenance_version": "2.0",
            "skill_type": "stack",
            "source_root": "/path/to/multi",
            "source_commit": "deadbeef",
            "source_ref": "main",
            "entries": [{"source_file": "lib-a/x.ts"}],
            "reexport_map": {"_X": "Y"},
        }
        result = mod.normalize(data)
        assert result["is_stack_skill"] is True
        assert result["legacy_stack_provenance"] is False
        assert result["reexport_map"] == {"_X": "Y"}

    def test_legacy_v1_stack(self) -> None:
        data = {
            "provenance_version": "1",
            "libraries": ["lib-a", "lib-b"],
            "entries": [],
        }
        result = mod.normalize(data)
        assert result["is_stack_skill"] is True
        assert result["legacy_stack_provenance"] is True

    def test_empty_map_defaults(self) -> None:
        result = mod.normalize({})
        assert result == {
            "bounded_scan_files": [],
            "is_stack_skill": False,
            "legacy_stack_provenance": False,
            "source_root": None,
            "baseline_commit": None,
            "baseline_ref": None,
            "reexport_map": {},
        }

    def test_non_string_scalars_become_null(self) -> None:
        data = {"source_root": 42, "source_commit": None, "source_ref": True}
        result = mod.normalize(data)
        assert result["source_root"] is None
        assert result["baseline_commit"] is None
        assert result["baseline_ref"] is None


# --------------------------------------------------------------------------
# load_provenance error paths
# --------------------------------------------------------------------------


class TestLoadProvenance:
    def test_loads_object(self, tmp_path: Path) -> None:
        path = _write_json(tmp_path / "p.json", {"source_root": "/x"})
        assert mod.load_provenance(path) == {"source_root": "/x"}

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        import pytest

        with pytest.raises(ValueError, match="malformed JSON"):
            mod.load_provenance(path)

    def test_top_level_array_raises(self, tmp_path: Path) -> None:
        path = _write_json(tmp_path / "arr.json", [])
        import pytest

        with pytest.raises(ValueError, match="must be a JSON object"):
            mod.load_provenance(path)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        import pytest

        with pytest.raises(ValueError, match="failed to read"):
            mod.load_provenance(tmp_path / "nope.json")


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
    def test_normalize_emits_json(self, tmp_path: Path) -> None:
        path = _write_json(
            tmp_path / "p.json",
            {
                "provenance_version": "2.0",
                "source_root": "/r",
                "source_commit": "abc",
                "source_ref": "v1",
                "entries": [{"source_file": "src/a.ts"}],
            },
        )
        result = _run_cli("normalize", str(path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["bounded_scan_files"] == ["src/a.ts"]
        assert payload["source_root"] == "/r"
        assert payload["baseline_commit"] == "abc"
        assert payload["baseline_ref"] == "v1"
        assert payload["is_stack_skill"] is False

    def test_normalize_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("normalize", str(tmp_path / "missing.json"))
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_normalize_malformed_exits_1(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{nope", encoding="utf-8")
        result = _run_cli("normalize", str(path))
        assert result.returncode == 1
        assert "malformed JSON" in result.stderr

    def test_normalize_empty_object_succeeds(self, tmp_path: Path) -> None:
        # well-formed but empty input should produce empty/null defaults
        path = _write_json(tmp_path / "p.json", {})
        result = _run_cli("normalize", str(path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["bounded_scan_files"] == []
        assert payload["source_root"] is None
