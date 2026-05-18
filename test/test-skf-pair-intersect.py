#!/usr/bin/env python3
"""Tests for skf-pair-intersect.py.

Covers:
  - compute_pairs: two-lib overlap, three-lib pairwise overlap, empty-
    intersection silence, stable ordering
  - intersect: Top-K cap with truncated/total_pairs flags
  - validate_libraries: structural errors (not-array, missing name, missing
    files, non-string entries)
  - CLI: file input, stdin (-) piping, --top-k override, exit codes
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-pair-intersect.py"

spec = importlib.util.spec_from_file_location("skf_pair_intersect", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _lib(name: str, files: list[str]) -> dict:
    return {"name": name, "files": files}


# --------------------------------------------------------------------------
# compute_pairs
# --------------------------------------------------------------------------


class TestComputePairs:
    def test_two_libs_overlap(self) -> None:
        libs = [
            _lib("react", ["src/App.tsx", "src/index.tsx", "src/utils.ts"]),
            _lib("react-router", ["src/App.tsx", "src/router.tsx"]),
        ]
        pairs = mod.compute_pairs(libs)
        assert pairs == [
            {
                "a": "react",
                "b": "react-router",
                "intersection_count": 1,
                "files": ["src/App.tsx"],
            }
        ]

    def test_three_libs_all_pairwise_overlap(self) -> None:
        # a-b: 2 files, a-c: 1 file, b-c: 3 files → sorted DESC by count
        libs = [
            _lib("a", ["f1", "f2", "f3"]),
            _lib("b", ["f1", "f2", "f4", "f5", "f6"]),
            _lib("c", ["f3", "f4", "f5", "f6"]),
        ]
        pairs = mod.compute_pairs(libs)
        assert [(p["a"], p["b"], p["intersection_count"]) for p in pairs] == [
            ("b", "c", 3),
            ("a", "b", 2),
            ("a", "c", 1),
        ]
        # files within a pair are sorted ASC
        b_c = next(p for p in pairs if p["a"] == "b" and p["b"] == "c")
        assert b_c["files"] == ["f4", "f5", "f6"]

    def test_empty_intersection_is_silent(self) -> None:
        libs = [
            _lib("a", ["f1", "f2"]),
            _lib("b", ["f3", "f4"]),
        ]
        assert mod.compute_pairs(libs) == []

    def test_stable_ordering_count_tie(self) -> None:
        # three pairs all with intersection_count=1 → sorted by (a, b) ASC
        libs = [
            _lib("alpha", ["shared"]),
            _lib("beta", ["shared"]),
            _lib("gamma", ["shared"]),
        ]
        pairs = mod.compute_pairs(libs)
        names = [(p["a"], p["b"]) for p in pairs]
        assert names == [("alpha", "beta"), ("alpha", "gamma"), ("beta", "gamma")]

    def test_deterministic_across_input_order(self) -> None:
        # same logical input, different input ordering → same output
        libs_1 = [
            _lib("zeta", ["f1", "f2"]),
            _lib("alpha", ["f1", "f3"]),
        ]
        libs_2 = [
            _lib("alpha", ["f3", "f1"]),
            _lib("zeta", ["f2", "f1"]),
        ]
        assert mod.compute_pairs(libs_1) == mod.compute_pairs(libs_2)

    def test_empty_libraries(self) -> None:
        assert mod.compute_pairs([]) == []

    def test_single_library(self) -> None:
        # one library → no pairs possible
        assert mod.compute_pairs([_lib("solo", ["a", "b", "c"])]) == []

    def test_duplicate_paths_in_files_are_deduped(self) -> None:
        # the per-library file lists shouldn't normally have duplicates, but
        # we de-dup defensively by going through set()
        libs = [
            _lib("a", ["f1", "f1", "f2"]),
            _lib("b", ["f1", "f2", "f2"]),
        ]
        pairs = mod.compute_pairs(libs)
        assert pairs == [{
            "a": "a", "b": "b", "intersection_count": 2, "files": ["f1", "f2"],
        }]


# --------------------------------------------------------------------------
# intersect (with Top-K cap)
# --------------------------------------------------------------------------


class TestIntersect:
    def test_no_truncation_when_under_cap(self) -> None:
        libs = [_lib("a", ["f"]), _lib("b", ["f"])]
        result = mod.intersect(libs, top_k=20)
        assert result == {
            "pairs": [{"a": "a", "b": "b", "intersection_count": 1, "files": ["f"]}],
            "truncated": False,
            "total_pairs": 1,
        }

    def test_truncation_at_default_top_k_20(self) -> None:
        # construct 25 non-empty-intersection pairs by giving each lib a
        # shared file with a single "hub" library
        hub = _lib("hub", [f"f{i}" for i in range(25)])
        spokes = [_lib(f"spoke{i:02d}", [f"f{i}"]) for i in range(25)]
        result = mod.intersect([hub, *spokes], top_k=20)
        assert result["truncated"] is True
        assert result["total_pairs"] == 25
        assert len(result["pairs"]) == 20
        # all surviving pairs should still have intersection_count == 1 and
        # follow the (a, b) tie-break ordering — first 20 spokes alphabetically
        for p in result["pairs"]:
            assert p["intersection_count"] == 1
            assert p["a"] == "hub"
        spoke_names = [p["b"] for p in result["pairs"]]
        assert spoke_names == [f"spoke{i:02d}" for i in range(20)]

    def test_custom_top_k(self) -> None:
        hub = _lib("hub", [f"f{i}" for i in range(5)])
        spokes = [_lib(f"spoke{i}", [f"f{i}"]) for i in range(5)]
        result = mod.intersect([hub, *spokes], top_k=3)
        assert result["truncated"] is True
        assert result["total_pairs"] == 5
        assert len(result["pairs"]) == 3

    def test_top_k_equals_total_no_truncation(self) -> None:
        hub = _lib("hub", ["f1", "f2", "f3"])
        spokes = [_lib(f"s{i}", [f"f{i}"]) for i in range(1, 4)]
        result = mod.intersect([hub, *spokes], top_k=3)
        assert result["truncated"] is False
        assert result["total_pairs"] == 3
        assert len(result["pairs"]) == 3

    def test_empty_input_yields_empty_pairs(self) -> None:
        assert mod.intersect([], top_k=20) == {
            "pairs": [],
            "truncated": False,
            "total_pairs": 0,
        }


# --------------------------------------------------------------------------
# validate_libraries
# --------------------------------------------------------------------------


class TestValidateLibraries:
    def test_valid_input(self) -> None:
        raw = [{"name": "a", "files": ["x", "y"]}]
        assert mod.validate_libraries(raw) == [{"name": "a", "files": ["x", "y"]}]

    def test_backslash_paths_normalized_to_forward_slash(self) -> None:
        raw = [{"name": "a", "files": [r"src\App.tsx", "src/index.tsx"]}]
        result = mod.validate_libraries(raw)
        assert result[0]["files"] == ["src/App.tsx", "src/index.tsx"]

    def test_not_array_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="must be a JSON array"):
            mod.validate_libraries({"name": "a"})

    def test_entry_not_object_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="not an object"):
            mod.validate_libraries(["not an object"])

    def test_missing_name_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="required `name`"):
            mod.validate_libraries([{"files": ["x"]}])

    def test_empty_name_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="required `name`"):
            mod.validate_libraries([{"name": "", "files": ["x"]}])

    def test_missing_files_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="required `files` array"):
            mod.validate_libraries([{"name": "a"}])

    def test_files_not_array_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="required `files` array"):
            mod.validate_libraries([{"name": "a", "files": "x"}])

    def test_file_entry_not_string_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="not a string"):
            mod.validate_libraries([{"name": "a", "files": ["x", 42]}])


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(
    *args: str, stdin_text: str | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        input=stdin_text,
        check=False,
    )


class TestCli:
    def test_intersect_from_file(self, tmp_path: Path) -> None:
        libs_path = tmp_path / "libs.json"
        libs_path.write_text(
            json.dumps([
                {"name": "react", "files": ["src/App.tsx", "src/index.tsx"]},
                {"name": "react-router", "files": ["src/App.tsx"]},
            ]),
            encoding="utf-8",
        )
        result = _run_cli("intersect", "--libraries", str(libs_path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["truncated"] is False
        assert payload["total_pairs"] == 1
        assert payload["pairs"][0]["a"] == "react"
        assert payload["pairs"][0]["b"] == "react-router"
        assert payload["pairs"][0]["files"] == ["src/App.tsx"]

    def test_intersect_from_stdin(self, tmp_path: Path) -> None:
        stdin = json.dumps([
            {"name": "alpha", "files": ["f1", "f2"]},
            {"name": "beta", "files": ["f1", "f2"]},
        ])
        result = _run_cli("intersect", "--libraries", "-", stdin_text=stdin)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["pairs"] == [{
            "a": "alpha",
            "b": "beta",
            "intersection_count": 2,
            "files": ["f1", "f2"],
        }]

    def test_intersect_top_k_override(self, tmp_path: Path) -> None:
        # 25 pairs → top-k=20 default → truncated=true, len=20
        hub_files = [f"f{i:02d}" for i in range(25)]
        libs = [{"name": "hub", "files": hub_files}]
        for i in range(25):
            libs.append({"name": f"spoke{i:02d}", "files": [f"f{i:02d}"]})
        libs_path = tmp_path / "libs.json"
        libs_path.write_text(json.dumps(libs), encoding="utf-8")
        result = _run_cli("intersect", "--libraries", str(libs_path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["truncated"] is True
        assert payload["total_pairs"] == 25
        assert len(payload["pairs"]) == 20

    def test_intersect_top_k_explicit_override(self, tmp_path: Path) -> None:
        libs = [
            {"name": "hub", "files": ["f1", "f2", "f3", "f4", "f5"]},
            {"name": "a", "files": ["f1"]},
            {"name": "b", "files": ["f2"]},
            {"name": "c", "files": ["f3"]},
            {"name": "d", "files": ["f4"]},
            {"name": "e", "files": ["f5"]},
        ]
        libs_path = tmp_path / "libs.json"
        libs_path.write_text(json.dumps(libs), encoding="utf-8")
        result = _run_cli(
            "intersect", "--libraries", str(libs_path), "--top-k", "3"
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["truncated"] is True
        assert payload["total_pairs"] == 5
        assert len(payload["pairs"]) == 3

    def test_intersect_empty_input(self, tmp_path: Path) -> None:
        libs_path = tmp_path / "libs.json"
        libs_path.write_text("[]", encoding="utf-8")
        result = _run_cli("intersect", "--libraries", str(libs_path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload == {"pairs": [], "truncated": False, "total_pairs": 0}

    def test_intersect_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli(
            "intersect", "--libraries", str(tmp_path / "missing.json")
        )
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_intersect_malformed_json_exits_1(self, tmp_path: Path) -> None:
        libs_path = tmp_path / "libs.json"
        libs_path.write_text("{not json", encoding="utf-8")
        result = _run_cli("intersect", "--libraries", str(libs_path))
        assert result.returncode == 1
        assert "malformed JSON" in result.stderr

    def test_intersect_missing_name_exits_1(self, tmp_path: Path) -> None:
        libs_path = tmp_path / "libs.json"
        libs_path.write_text(
            json.dumps([{"files": ["f1"]}]), encoding="utf-8"
        )
        result = _run_cli("intersect", "--libraries", str(libs_path))
        assert result.returncode == 1
        assert "name" in result.stderr

    def test_intersect_missing_files_field_exits_1(self, tmp_path: Path) -> None:
        libs_path = tmp_path / "libs.json"
        libs_path.write_text(
            json.dumps([{"name": "a"}]), encoding="utf-8"
        )
        result = _run_cli("intersect", "--libraries", str(libs_path))
        assert result.returncode == 1
        assert "files" in result.stderr

    def test_intersect_negative_top_k_exits_1(self, tmp_path: Path) -> None:
        libs_path = tmp_path / "libs.json"
        libs_path.write_text("[]", encoding="utf-8")
        result = _run_cli(
            "intersect", "--libraries", str(libs_path), "--top-k", "-1"
        )
        assert result.returncode == 1
        assert "top-k" in result.stderr

    def test_subprocess_reproducible_output(self, tmp_path: Path) -> None:
        libs = [
            {"name": "z", "files": ["f1", "f2"]},
            {"name": "a", "files": ["f1", "f2"]},
            {"name": "m", "files": ["f1"]},
        ]
        libs_path = tmp_path / "libs.json"
        libs_path.write_text(json.dumps(libs), encoding="utf-8")
        r1 = _run_cli("intersect", "--libraries", str(libs_path))
        r2 = _run_cli("intersect", "--libraries", str(libs_path))
        assert r1.returncode == 0 and r2.returncode == 0
        assert r1.stdout == r2.stdout
