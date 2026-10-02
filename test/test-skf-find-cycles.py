#!/usr/bin/env python3
"""Tests for skf-find-cycles.py.

Covers:
  - find_cycles: 2-cycle, 3-cycle canonicalisation, DAG (no cycles), two
    distinct cycles sharing a node, rotation of an input cycle not double-
    counted, self-loop, disconnected components, deterministic ordering
  - parse_edges: structural validation → InputError
  - --skip-mutual and --exclude-edges (verify-stack's cycle rows): cycles
    built only from mutual edges left out, rejected directions dropped
    before the traversal
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

    def test_skip_mutual_keeps_a_cycle_with_a_one_way_edge(self) -> None:
        # A and B cite each other (Check 4 evidence for their pair, not a
        # circular dependency); A -> B -> C -> A and the self-loop stay.
        edges = [("A", "B"), ("B", "A"), ("B", "C"), ("C", "A"), ("D", "D")]
        assert mod.find_cycles(edges)["cycles"] == [
            ["D", "D"], ["A", "B", "A"], ["A", "B", "C", "A"]]
        result = mod.find_cycles(edges, skip_mutual=True)
        assert result == {"cycles": [["D", "D"], ["A", "B", "C", "A"]], "cycle_count": 2}

    def test_skip_mutual_leaves_out_a_loop_of_mutual_pairs(self) -> None:
        # Three skills that all cite each other: both directions of the
        # triangle are built from mutual edges only, as each pair is.
        edges = [("A", "B"), ("B", "A"), ("B", "C"), ("C", "B"), ("A", "C"), ("C", "A")]
        assert mod.find_cycles(edges)["cycle_count"] == 5
        assert mod.find_cycles(edges, skip_mutual=True) == {"cycles": [], "cycle_count": 0}
        # C no longer cites A: A -> B -> C -> A loses its edge C -> A, and
        # A -> C -> B -> A stays, as A -> C is now one-way.
        one_way = [e for e in edges if e != ("C", "A")]
        assert mod.find_cycles(one_way, skip_mutual=True)["cycles"] == [["A", "C", "B", "A"]]

    def test_skip_mutual_with_only_mutual_pairs_finds_none(self) -> None:
        edges = [("A", "B"), ("B", "A"), ("X", "Y"), ("Y", "X")]
        assert mod.find_cycles(edges, skip_mutual=True) == {"cycles": [], "cycle_count": 0}


class TestExcludeEdges:
    def test_drops_every_occurrence_and_keeps_order(self) -> None:
        edges = [("A", "B"), ("B", "C"), ("A", "B"), ("C", "A")]
        assert mod.exclude_edges(edges, [("A", "B")]) == [("B", "C"), ("C", "A")]

    def test_direction_matters(self) -> None:
        # Leaving out B -> A keeps A -> B.
        assert mod.exclude_edges([("A", "B"), ("B", "A")], [("B", "A")]) == [("A", "B")]

    def test_an_absent_edge_changes_nothing(self) -> None:
        edges = [("A", "B"), ("B", "A")]
        assert mod.exclude_edges(edges, [("X", "Y")]) == edges

    def test_a_rejected_direction_breaks_the_cycle(self) -> None:
        edges = [("A", "B"), ("B", "C"), ("C", "A")]
        assert mod.find_cycles(mod.exclude_edges(edges, [("C", "A")]))["cycles"] == []


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

    def test_exclude_edges_and_skip_mutual_over_a_citations_file(self, tmp_path: Path) -> None:
        # verify-stack passes the scanner's citations file as it is: its other
        # keys are ignored. zod cites next only through the common word, so
        # that direction is excluded, and react-query and zod cite each other.
        citations = tmp_path / "citations.json"
        citations.write_bytes(json.dumps({
            "citations": [{"from": "zod", "to": "next", "hits": []}],
            "edges": [["react-query", "zod"], ["zod", "react-query"], ["zod", "next"],
                      ["next", "react-query"], ["react-query", "next"]],
            "warnings": [],
        }).encode("utf-8"))
        rejected = tmp_path / "rejected.json"
        rejected.write_bytes(json.dumps({"edges": [["zod", "next"]]}).encode("utf-8"))
        plain = _run_cli("find", "--edges", str(citations))
        assert plain.returncode == 0, plain.stderr
        assert json.loads(plain.stdout)["cycles"] == [
            ["next", "react-query", "next"], ["react-query", "zod", "react-query"],
            ["next", "react-query", "zod", "next"]]
        result = _run_cli("find", "--edges", str(citations), "--exclude-edges", str(rejected),
                          "--skip-mutual")
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {"cycles": [], "cycle_count": 0}
        empty = tmp_path / "none.json"
        empty.write_bytes(json.dumps({"edges": []}).encode("utf-8"))
        kept = _run_cli("find", "--edges", str(citations), "--exclude-edges", str(empty),
                        "--skip-mutual")
        assert json.loads(kept.stdout)["cycles"] == [["next", "react-query", "zod", "next"]]

    def test_exclude_edges_from_stdin(self, tmp_path: Path) -> None:
        edges = tmp_path / "edges.json"
        edges.write_bytes(
            json.dumps({"edges": [["A", "B"], ["B", "C"], ["C", "A"]]}).encode("utf-8"))
        result = _run_cli("find", "--edges", str(edges), "--exclude-edges", "-",
                          stdin_text=json.dumps({"edges": [["B", "C"]]}))
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["cycle_count"] == 0

    def test_exclude_edges_wrong_shape_exits_2(self, tmp_path: Path) -> None:
        edges = tmp_path / "edges.json"
        edges.write_bytes(json.dumps({"edges": [["A", "B"]]}).encode("utf-8"))
        bad = tmp_path / "bad.json"
        bad.write_bytes(json.dumps([["A", "B"]]).encode("utf-8"))
        result = _run_cli("find", "--edges", str(edges), "--exclude-edges", str(bad))
        assert result.returncode == 2
        assert "--exclude-edges" in result.stderr and "must be a JSON object" in result.stderr
        missing = _run_cli("find", "--edges", str(edges),
                           "--exclude-edges", str(tmp_path / "nope.json"))
        assert missing.returncode == 2 and "--exclude-edges file not found" in missing.stderr

    def test_both_inputs_from_stdin_exit_2(self) -> None:
        result = _run_cli("find", "--edges", "-", "--exclude-edges", "-", stdin_text="{}")
        assert result.returncode == 2
        assert "cannot both read from stdin" in result.stderr

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
