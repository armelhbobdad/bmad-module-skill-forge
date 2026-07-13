#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Find Cycles — enumerate the simple directed cycles in a pair graph.

`skf-verify-stack`'s `integrations.md` §4 (Cross-Reference Each Integration
Pair → Cycle detection) asks the LLM to build a directed pair graph — an edge
`A → B` exists when skill A literally cites skill B via Check 4 — and then to
"run cycle detection (DFS with visited + recursion stack)", appending one
synthetic `Risky` verdict row per circular integration dependency found.

Deciding *which* edges exist is a semantic judgment (Check-4 literal-citation
analysis) and stays in the prompt. But once the edge set is fixed, the set of
directed cycles is fully determined — a graph traversal with exactly one
correct answer per edge set. In-prompt DFS silently misses real multi-hop
cycles or invents spurious ones as the pair count grows; this helper makes the
traversal deterministic and unit-testable. The prompt hands over the edges as
JSON and appends the synthetic rows from `cycles[]` — no traversal by hand.

Subcommand:
  find --edges <json-file-or-'-'>
      --edges  path to the edges JSON, or '-' to read from stdin.

      Input shape (the Check-4 citation edges, one [from, to] pair each):
        {"edges": [["A", "B"], ["B", "C"], ["C", "A"], ...]}

      Emit JSON:
        {
          "cycles": [["A", "B", "C", "A"], ...],
          "cycle_count": N
        }

      Each cycle is a closed node path: the first node is repeated at the end
      (`A → B → C → A` renders as ["A", "B", "C", "A"]). Every simple directed
      cycle is enumerated exactly once — de-duplicated across its rotations by
      canonicalising to the lexicographically-minimal rotation. `cycles[]` is
      sorted by length ASC then lexicographically for stable, reproducible
      ordering. A self-loop edge (["A", "A"]) is a 1-node cycle ["A", "A"].

CLI examples:
  uv run skf-find-cycles.py find --edges edges.json
  echo '{"edges": [["A","B"],["B","A"]]}' | uv run skf-find-cycles.py find --edges -

Exit codes:
  0  — operation succeeded (including: no cycles / empty edge set → empty list)
  2  — malformed input (bad JSON, wrong shape, non-string node) or internal
       error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


class InputError(Exception):
    """A malformed-input error → exit code 2."""


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------


def parse_edges(payload: object) -> list[tuple[str, str]]:
    """Validate and normalise the edges payload.

    Accepts `{"edges": [[from, to], ...]}`; each edge must be a two-element
    array of non-empty strings. Raises InputError on any structural defect.
    Returns a list of (from, to) tuples (order preserved; duplicates kept —
    they collapse during adjacency construction).
    """
    if not isinstance(payload, dict):
        raise InputError(
            f"input must be a JSON object with an `edges` key; "
            f"got {type(payload).__name__}"
        )
    edges = payload.get("edges")
    if not isinstance(edges, list):
        raise InputError("input `edges` must be a JSON array of [from, to] pairs")
    normalized: list[tuple[str, str]] = []
    for idx, edge in enumerate(edges):
        if not isinstance(edge, list) or len(edge) != 2:
            raise InputError(
                f"edges[{idx}] must be a two-element [from, to] array; got {edge!r}"
            )
        src, dst = edge
        if not isinstance(src, str) or not src:
            raise InputError(f"edges[{idx}][0] must be a non-empty string; got {src!r}")
        if not isinstance(dst, str) or not dst:
            raise InputError(f"edges[{idx}][1] must be a non-empty string; got {dst!r}")
        normalized.append((src, dst))
    return normalized


# --------------------------------------------------------------------------
# Cycle enumeration
# --------------------------------------------------------------------------


def _canonicalize(cycle_nodes: list[str]) -> tuple[str, ...]:
    """Return the lexicographically-minimal rotation of a cycle's node list.

    `cycle_nodes` is the cycle without the closing repeat (e.g. ["B","C","A"]
    for B → C → A → B). All rotations describe the same directed cycle; the
    minimal rotation is the stable de-duplication key ((A, B, C) here).
    """
    n = len(cycle_nodes)
    rotations = [tuple(cycle_nodes[i:] + cycle_nodes[:i]) for i in range(n)]
    return min(rotations)


def find_cycles(edges: list[tuple[str, str]]) -> dict:
    """Enumerate every simple directed cycle in the edge set.

    Deterministic: same edge set → byte-identical output. Runs a DFS from each
    node (in sorted order) tracking the current recursion path; whenever the
    walk returns to its start node a cycle is recorded, canonicalised to its
    minimal rotation, and de-duplicated. Graphs here are small pair graphs, so
    the exhaustive enumeration is inexpensive.
    """
    # Build sorted, de-duplicated adjacency for deterministic traversal.
    adj: dict[str, list[str]] = {}
    nodes: set[str] = set()
    for src, dst in edges:
        adj.setdefault(src, [])
        if dst not in adj[src]:
            adj[src].append(dst)
        nodes.add(src)
        nodes.add(dst)
    for src in adj:
        adj[src].sort()

    seen: set[tuple[str, ...]] = set()

    def dfs(start: str, current: str, path: list[str], on_stack: set[str]) -> None:
        for nxt in adj.get(current, ()):
            if nxt == start:
                canon = _canonicalize(path)
                seen.add(canon)
            elif nxt not in on_stack:
                on_stack.add(nxt)
                path.append(nxt)
                dfs(start, nxt, path, on_stack)
                path.pop()
                on_stack.discard(nxt)

    for start in sorted(nodes):
        dfs(start, start, [start], {start})

    # Stable output order: by cycle length, then lexicographically.
    ordered = sorted(seen, key=lambda c: (len(c), c))
    cycles = [list(c) + [c[0]] for c in ordered]
    return {"cycles": cycles, "cycle_count": len(cycles)}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_source(source: str) -> str:
    """Read text from a file path or stdin (if source == '-')."""
    if source == "-":
        try:
            return sys.stdin.read()
        except OSError as exc:
            raise InputError(f"failed to read --edges from stdin: {exc}") from exc
    path = Path(source)
    if not path.is_file():
        raise InputError(f"--edges file not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"failed to read --edges file {path}: {exc}") from exc


def _cmd_find(args: argparse.Namespace) -> int:
    text = _read_source(args.edges)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"malformed JSON in --edges input: {exc}") from exc
    edges = parse_edges(payload)
    result = find_cycles(edges)
    if args.verbose:
        print(
            f"analyzed {len(edges)} edge(s); found {result['cycle_count']} cycle(s)",
            file=sys.stderr,
        )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-find-cycles",
        description=(
            "Enumerate the simple directed cycles in an integration pair graph "
            "(skf-verify-stack integrations.md §4 cycle detection)."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_find = sub.add_parser(
        "find",
        help="emit the de-duplicated simple directed cycles as JSON",
    )
    p_find.add_argument(
        "--edges",
        required=True,
        help=(
            "path to the edges JSON, or '-' for stdin. "
            'Shape: {"edges": [["<from>", "<to>"], ...]}'
        ),
    )
    p_find.add_argument(
        "--verbose",
        action="store_true",
        help="print a one-line summary to stderr",
    )
    p_find.set_defaults(func=_cmd_find)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — last-resort guard → exit 2
        print(f"internal error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
