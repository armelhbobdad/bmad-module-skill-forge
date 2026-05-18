# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Pair Intersect — compute file-list intersections between library pairs.

`detect-integrations.md` §1 ("File-list intersection fast path") asks the LLM
to prune the N*(N-1)/2 pair-grep matrix by intersecting the per-library file
lists that step 3 import-count extraction already produced. At N≈21 this
collapses ~210 prescribed pair greps to a handful of non-empty-intersection
pairs in typical codebases; the LLM only needs to run further grep passes
against those.

This script extracts that intersection from prose-orchestrated work to a
deterministic helper. The LLM still composes the user-facing warning when
the Top-K cap kicks in — the script just flags `truncated: true` so the
caller knows there's something to warn about.

Subcommand:
  intersect --libraries <json-file-or-'-'> [--top-k N]
      Read a libraries JSON (either from <json-file> or stdin if '-') of the
      shape:
        [{"name": "<lib>", "files": ["<path>", ...]}, ...]
      where each library entry lists the project files that import it (the
      per-library file enumeration from detect-integrations.md step 3).

      Emit JSON:
        {
          "pairs": [
            {"a": "<lib>", "b": "<lib>", "intersection_count": N,
             "files": ["<rel-path-forward-slash>", ...]},
            ...
          ],
          "truncated": false,
          "total_pairs": <full non-empty-intersection count before cap>
        }

      Pairs are computed for each unordered pair (a, b) with a < b
      lexicographically; only non-empty intersections are emitted. The pairs
      list is sorted by intersection_count DESC, then by (a, b) ASC for
      stable, reproducible ordering.

      Top-K cap: default --top-k 20 (matches detect-integrations.md §1's
      "Top-K cap at 20 with explicit warning"). If the full count exceeds
      the cap, output is truncated to top --top-k pairs and `truncated`
      becomes true.

CLI examples:
  uv run skf-pair-intersect.py intersect --libraries libs.json
  cat libs.json | uv run skf-pair-intersect.py intersect --libraries -
  uv run skf-pair-intersect.py intersect --libraries libs.json --top-k 50

Exit codes:
  0  — operation succeeded (including: empty input → empty pairs list)
  1  — user error (bad JSON, missing required `name`/`files` field on any
       library entry, file not readable)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEFAULT_TOP_K = 20


# --------------------------------------------------------------------------
# Pair intersection
# --------------------------------------------------------------------------


def validate_libraries(libraries: object) -> list[dict]:
    """Validate the libraries input is a list of {name, files} records.

    Returns the list with each entry's `files` normalized to a list of
    forward-slash strings. Raises ValueError on any structural defect.
    """
    if not isinstance(libraries, list):
        raise ValueError(
            f"libraries input must be a JSON array; got {type(libraries).__name__}"
        )
    normalized: list[dict] = []
    for idx, entry in enumerate(libraries):
        if not isinstance(entry, dict):
            raise ValueError(
                f"library entry at index {idx} is not an object: {entry!r}"
            )
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"library entry at index {idx} missing required `name` field"
            )
        files = entry.get("files")
        if not isinstance(files, list):
            raise ValueError(
                f"library entry {name!r} missing required `files` array"
            )
        norm_files: list[str] = []
        for f_idx, f in enumerate(files):
            if not isinstance(f, str):
                raise ValueError(
                    f"library {name!r} files[{f_idx}] is not a string: {f!r}"
                )
            # normalize separators to forward slash for cross-platform
            # JSON output; preserves caller-supplied relative paths.
            norm_files.append(f.replace("\\", "/"))
        normalized.append({"name": name, "files": norm_files})
    return normalized


def compute_pairs(libraries: list[dict]) -> list[dict]:
    """For each unordered (a, b) with a < b lexicographically, compute the
    file-list intersection. Emit only pairs with non-empty intersections.

    The returned list is sorted by intersection_count DESC, then (a, b) ASC.
    """
    # sort libraries by name for stable iteration order
    sorted_libs = sorted(libraries, key=lambda lib: lib["name"])
    pairs: list[dict] = []
    n = len(sorted_libs)
    for i in range(n):
        for j in range(i + 1, n):
            a = sorted_libs[i]
            b = sorted_libs[j]
            # by sort order, a["name"] <= b["name"]; if equal we skip
            # (duplicate library names are silently collapsed into one
            # pair-with-itself, which is not an integration candidate).
            if a["name"] == b["name"]:
                continue
            set_a = set(a["files"])
            set_b = set(b["files"])
            intersection = sorted(set_a & set_b)
            if not intersection:
                continue
            pairs.append({
                "a": a["name"],
                "b": b["name"],
                "intersection_count": len(intersection),
                "files": intersection,
            })
    pairs.sort(key=lambda p: (-p["intersection_count"], p["a"], p["b"]))
    return pairs


def intersect(libraries: list[dict], top_k: int = DEFAULT_TOP_K) -> dict:
    """Compute pairs and apply Top-K cap."""
    all_pairs = compute_pairs(libraries)
    total = len(all_pairs)
    if top_k is not None and top_k >= 0 and total > top_k:
        return {
            "pairs": all_pairs[:top_k],
            "truncated": True,
            "total_pairs": total,
        }
    return {
        "pairs": all_pairs,
        "truncated": False,
        "total_pairs": total,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_libraries_source(source: str) -> object:
    """Read libraries JSON from a file path or stdin (if source == '-')."""
    if source == "-":
        try:
            text = sys.stdin.read()
        except OSError as exc:
            raise ValueError(f"failed to read libraries JSON from stdin: {exc}") from exc
    else:
        path = Path(source)
        if not path.is_file():
            raise ValueError(f"libraries file not found: {path}")
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"failed to read libraries file {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in libraries input: {exc}") from exc


def _cmd_intersect(args: argparse.Namespace) -> int:
    try:
        raw = _read_libraries_source(args.libraries)
        libraries = validate_libraries(raw)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.top_k < 0:
        print(f"error: --top-k must be >= 0; got {args.top_k}", file=sys.stderr)
        return 1
    result = intersect(libraries, top_k=args.top_k)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-pair-intersect",
        description=(
            "Compute file-list intersections between library pairs "
            "(detect-integrations.md §1 fast path)."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_int = sub.add_parser(
        "intersect",
        help="emit non-empty-intersection pairs as JSON, sorted DESC by count",
    )
    p_int.add_argument(
        "--libraries",
        required=True,
        help=(
            "path to libraries JSON, or '-' to read from stdin. "
            "Shape: [{\"name\": \"<lib>\", \"files\": [\"<path>\", ...]}, ...]"
        ),
    )
    p_int.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=(
            f"cap output at top N pairs by intersection_count (default {DEFAULT_TOP_K}); "
            "set 0 to allow only zero pairs (effectively a 'count-only' mode)"
        ),
    )
    p_int.set_defaults(func=_cmd_intersect)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
