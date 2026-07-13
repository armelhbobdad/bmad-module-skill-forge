#!/usr/bin/env python3
"""Tests for skf-find-cycles.py.

Covers:
  - find_cycles: 2-cycle, 3-cycle canonicalisation, DAG (no cycles), two
    distinct cycles sharing a node, rotation of an input cycle not double-
    counted, self-loop, disconnected components, deterministic ordering
  - parse_edges: structural validation → InputError
  - CLI: file input, stdin (-) piping, exit codes, reproducibility
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-find-cycles.py"

spec = importlib.util.spec_from_file_location("skf_find_cycles", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _cycle_set(result: dict) -> set[tuple[str, ...]]:
    """Reduce a result's cycles to a set of canonical (closing-repeat-stripped)
    tuples, so tests are order- and rotation-agnostic."""
    return {mod._canonicalize(c[:-1]) for c in result["cycles"]}


# --------------------------------------------------------------------------
# find_cycles — the canonical fixtures from the implementation brief test_idea
# --------------------------------------------------------------------------


class TestFindCycles:
    def test_two_cycle(self) -> None:
        # (1) A ⇄ B → exactly one 2-cycle.
        result = mod.find_cycles([("A", "B"), ("B", "A")])
        assert result["cycle_count"] == 1
        assert result["cycles"] == [["A", "B", "A"]]

    def test_three_cycle_canonicalized(self) -> None:
        # (2) A → B → C → A → exactly one cycle, canonicalised to A→B→C→A.
        result = mod.find_cycles([("A", "B"), ("B", "C"), ("C", "A")])
        assert result["cycle_count"] == 1
        assert result["cycles"] == [["A", "B", "C", "A"]]

    def test_three_cycle_canonical_regardless_of_input_start(self) -> None:
        # The same cycle expressed starting from B still canonicalises to the
        # A-rooted rotation.
        result = mod.find_cycles([("B", "C"), ("C", "A"), ("A", "B")])
        assert result["cycles"] == [["A", "B", "C", "A"]]

    def test_dag_has_no_cycles(self) -> None:
        # (3) A → B → C is acyclic → zero cycles.
        result = mod.find_cycles([("A", "B"), ("B", "C")])
        assert result == {"cycles": [], "cycle_count": 0}

    def test_two_distinct_cycles_sharing_a_node_plus_rotation(self) -> None:
        # (4) Cycle1: A→B→C→A ; Cycle2: A→D→A (share node A). The input also
        # includes a rotation of Cycle1's edges — the same edges, so no new
        # cycle — proving the rotation is not double-counted.
        edges = [
            ("A", "B"), ("B", "C"), ("C", "A"),   # cycle 1
            ("A", "D"), ("D", "A"),               # cycle 2 (shares A)
            ("B", "C"), ("C", "A"), ("A", "B"),   # rotation/duplicate of cycle 1
        ]
        result = mod.find_cycles(edges)
        assert result["cycle_count"] == 2
        assert _cycle_set(result) == {("A", "B", "C"), ("A", "D")}
        # Deterministic order: shorter cycle (A,D) before longer (A,B,C).
        assert result["cycles"] == [["A", "D", "A"], ["A", "B", "C", "A"]]

    def test_self_loop_is_a_one_node_cycle(self) -> None:
        result = mod.find_cycles([("A", "A")])
        assert result["cycles"] == [["A", "A"]]
        assert result["cycle_count"] == 1

    def test_empty_edges_no_cycles(self) -> None:
        assert mod.find_cycles([]) == {"cycles": [], "cycle_count": 0}

    def test_disconnected_components_each_cycle_found(self) -> None:
        # Two independent 2-cycles in disjoint components.
        edges = [("A", "B"), ("B", "A"), ("X", "Y"), ("Y", "X")]
        result = mod.find_cycles(edges)
        assert _cycle_set(result) == {("A", "B"), ("X", "Y")}
        assert result["cycle_count"] == 2

    def test_parallel_edges_collapse(self) -> None:
        # Duplicate A→B edges must not fabricate extra cycles.
        result = mod.find_cycles([("A", "B"), ("A", "B"), ("B", "A")])
        assert result["cycle_count"] == 1

    def test_deterministic_same_input(self) -> None:
        edges = [("C", "A"), ("A", "B"), ("B", "C"), ("A", "D"), ("D", "A")]
        r1 = mod.find_cycles(edges)
        r2 = mod.find_cycles(list(reversed(edges)))
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


# --------------------------------------------------------------------------
# parse_edges — structural validation
# --------------------------------------------------------------------------


class TestParseEdges:
    def test_valid(self) -> None:
        assert mod.parse_edges({"edges": [["A", "B"]]}) == [("A", "B")]

    def test_empty_edges_ok(self) -> None:
        assert mod.parse_edges({"edges": []}) == []

    def test_not_object_raises(self) -> None:
        import pytest

        with pytest.raises(mod.InputError, match="must be a JSON object"):
            mod.parse_edges([["A", "B"]])

    def test_edges_not_list_raises(self) -> None:
        import pytest

        with pytest.raises(mod.InputError, match="`edges` must be a JSON array"):
            mod.parse_edges({"edges": "nope"})

    def test_edge_wrong_arity_raises(self) -> None:
        import pytest

        with pytest.raises(mod.InputError, match="two-element"):
            mod.parse_edges({"edges": [["A", "B", "C"]]})

    def test_edge_non_string_node_raises(self) -> None:
        import pytest

        with pytest.raises(mod.InputError, match="non-empty string"):
            mod.parse_edges({"edges": [["A", 42]]})

    def test_edge_empty_node_raises(self) -> None:
        import pytest

        with pytest.raises(mod.InputError, match="non-empty string"):
            mod.parse_edges({"edges": [["", "B"]]})


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str, stdin_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        input=stdin_text,
        check=False,
    )


class TestCli:
    def test_find_from_file(self, tmp_path: Path) -> None:
        edges = tmp_path / "edges.json"
        edges.write_text(
            json.dumps({"edges": [["A", "B"], ["B", "C"], ["C", "A"]]}),
            encoding="utf-8",
        )
        result = _run_cli("find", "--edges", str(edges))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload == {"cycles": [["A", "B", "C", "A"]], "cycle_count": 1}

    def test_find_from_stdin(self) -> None:
        result = _run_cli(
            "find", "--edges", "-",
            stdin_text=json.dumps({"edges": [["A", "B"], ["B", "A"]]}),
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload == {"cycles": [["A", "B", "A"]], "cycle_count": 1}

    def test_dag_from_stdin(self) -> None:
        result = _run_cli(
            "find", "--edges", "-",
            stdin_text=json.dumps({"edges": [["A", "B"], ["B", "C"]]}),
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {"cycles": [], "cycle_count": 0}

    def test_malformed_json_exits_2(self) -> None:
        result = _run_cli("find", "--edges", "-", stdin_text="{not json")
        assert result.returncode == 2
        assert "malformed JSON" in result.stderr

    def test_wrong_shape_exits_2(self) -> None:
        result = _run_cli(
            "find", "--edges", "-", stdin_text=json.dumps([["A", "B"]])
        )
        assert result.returncode == 2
        assert "must be a JSON object" in result.stderr

    def test_missing_file_exits_2(self, tmp_path: Path) -> None:
        result = _run_cli("find", "--edges", str(tmp_path / "nope.json"))
        assert result.returncode == 2
        assert "not found" in result.stderr

    def test_reproducible_output(self, tmp_path: Path) -> None:
        edges = tmp_path / "edges.json"
        edges.write_text(
            json.dumps({"edges": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "D"], ["D", "A"]]}),
            encoding="utf-8",
        )
        r1 = _run_cli("find", "--edges", str(edges))
        r2 = _run_cli("find", "--edges", str(edges))
        assert r1.returncode == 0 and r2.returncode == 0
        assert r1.stdout == r2.stdout
