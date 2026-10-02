# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Pair Intersect — compute file-list intersections between library pairs.

`detect-integrations.md` §1 prunes the N*(N-1)/2 library pairs by
intersecting the per-library file lists that step 3's `skf-count-imports.py`
run already produced. At N≈21 this collapses ~210 pairs to a handful of
non-empty-intersection pairs in typical codebases, and each pair's `files`
are its co-import files: §2 reads them, with their import lines from step
3's counts, and greps nothing again.

This script extracts that intersection from prose-orchestrated work to a
deterministic helper. The LLM still composes the user-facing warning when
the Top-K cap kicks in — the script just flags `truncated: true` so the
caller knows there's something to warn about.

Subcommand:
  intersect (--libraries <json-file-or-'-'> | --counts <json-file-or-'-'>)
            [--only a,b] [--top-k N]
      Read the libraries (from the file, or stdin if '-') in one of two
      shapes:
        --libraries  [{"name": "<lib>", "files": ["<path>", ...]}, ...]
                     where each library entry lists the project files that
                     import it (`skf-count-imports.py count --format
                     libraries` prints this list).
        --counts     the `skf-count-imports.py count` envelope as it is
                     (its default `full` format): each `dependencies[]`
                     entry, then each `units[]` entry, is a library whose
                     files are its `files[]` ({path, line}). Entries that
                     share a name are one library, with the first line each
                     file imports it on.
      --only names the libraries to pair, comma-separated (trimmed, empty
      items dropped); every other library is left out, and a name the input
      does not hold has no files, so it joins no pair.

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
      With --counts, each `files` entry is instead
        {"path": "<rel-path-forward-slash>", "line_a": N, "line_b": N}
      where `line_a` and `line_b` are the first lines of that file that
      import `a` and `b`: the co-import files of the pair, with their lines.

      Pairs are computed for each unordered pair (a, b) with a < b
      lexicographically; only non-empty intersections are emitted. The pairs
      list is sorted by intersection_count DESC, then by (a, b) ASC for
      stable, reproducible ordering; the files of a pair are sorted by path.

      Top-K cap: default --top-k 20 (matches detect-integrations.md §1's
      "Top-K cap at 20 with explicit warning"). If the full count exceeds
      the cap, output is truncated to top --top-k pairs and `truncated`
      becomes true.

CLI examples:
  uv run skf-pair-intersect.py intersect --libraries libs.json
  cat libs.json | uv run skf-pair-intersect.py intersect --libraries -
  uv run skf-pair-intersect.py intersect --libraries libs.json --top-k 50
  uv run skf-count-imports.py count . --deps manifests.json \\
    | uv run skf-pair-intersect.py intersect --counts - --only "react,zustand"

Exit codes:
  0  - operation succeeded (including: empty input → empty pairs list)
  1  - user error (bad JSON, missing required `name`/`files` field on any
       library entry, a --counts input that is not the count envelope or
       a file entry that is not a {path, line} object, file not readable)
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


def libraries_from_counts(counts: object) -> list[dict]:
    """The libraries of a `skf-count-imports.py count` envelope.

    Each `dependencies[]` entry, then each `units[]` entry, becomes a
    {name, files, lines} record: `lines` maps each forward-slash path to the
    first line that imports the library. Entries that share a name merge,
    keeping the lower line. Raises ValueError on any structural defect.
    """
    if not isinstance(counts, dict) or not isinstance(counts.get("dependencies"), list):
        raise ValueError(
            "counts input must be the skf-count-imports.py count envelope "
            "(an object with a `dependencies` array)"
        )
    units = counts.get("units", [])
    if not isinstance(units, list):
        raise ValueError("counts `units` is not an array")
    merged: dict[str, dict[str, int]] = {}
    for idx, entry in enumerate(counts["dependencies"] + units):
        if not isinstance(entry, dict):
            raise ValueError(f"counts entry at index {idx} is not an object: {entry!r}")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"counts entry at index {idx} missing required `name` field")
        files = entry.get("files")
        if not isinstance(files, list):
            raise ValueError(f"counts entry {name!r} missing required `files` array")
        lines = merged.setdefault(name, {})
        for f_idx, f in enumerate(files):
            line = f.get("line") if isinstance(f, dict) else None
            if (not isinstance(f, dict) or not isinstance(f.get("path"), str)
                    or not isinstance(line, int) or isinstance(line, bool)):
                raise ValueError(
                    f"counts entry {name!r} files[{f_idx}] is not a {{path, line}} object: {f!r}"
                )
            path = f["path"].replace("\\", "/")
            if path not in lines or line < lines[path]:
                lines[path] = line
    return [
        {"name": name, "files": sorted(lines), "lines": lines}
        for name, lines in merged.items()
    ]


def only(libraries: list[dict], names: list[str]) -> list[dict]:
    """The libraries `names` lists; a listed name with no library adds nothing."""
    keep = set(names)
    return [lib for lib in libraries if lib["name"] in keep]


def compute_pairs(libraries: list[dict]) -> list[dict]:
    """For each unordered (a, b) with a < b lexicographically, compute the
    file-list intersection. Emit only pairs with non-empty intersections.

    The returned list is sorted by intersection_count DESC, then (a, b) ASC.
    When both libraries carry `lines` (the --counts input), each file is a
    {path, line_a, line_b} object instead of a path.
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
            files: list = intersection
            if "lines" in a and "lines" in b:
                files = [
                    {"path": path, "line_a": a["lines"][path], "line_b": b["lines"][path]}
                    for path in intersection
                ]
            pairs.append({
                "a": a["name"],
                "b": b["name"],
                "intersection_count": len(intersection),
                "files": files,
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


def _read_libraries_source(source: str, what: str = "libraries") -> object:
    """Read the input JSON from a file path or stdin (if source == '-')."""
    if source == "-":
        try:
            text = sys.stdin.read()
        except OSError as exc:
            raise ValueError(f"failed to read {what} JSON from stdin: {exc}") from exc
    else:
        path = Path(source)
        if not path.is_file():
            raise ValueError(f"{what} file not found: {path}")
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"failed to read {what} file {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {what} input: {exc}") from exc


def _cmd_intersect(args: argparse.Namespace) -> int:
    try:
        if args.counts is not None:
            libraries = libraries_from_counts(_read_libraries_source(args.counts, "counts"))
        else:
            libraries = validate_libraries(_read_libraries_source(args.libraries))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.only is not None:
        libraries = only(libraries, [n for n in (part.strip() for part in args.only.split(",")) if n])
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
    source = p_int.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--libraries",
        help=(
            "path to libraries JSON, or '-' to read from stdin. "
            "Shape: [{\"name\": \"<lib>\", \"files\": [\"<path>\", ...]}, ...]"
        ),
    )
    source.add_argument(
        "--counts",
        help=(
            "path to a skf-count-imports.py count envelope, or '-' to read from "
            "stdin; each pair's files then carry line_a and line_b"
        ),
    )
    p_int.add_argument(
        "--only",
        metavar="NAMES",
        help="comma-separated library names to pair; every other library is left out",
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
