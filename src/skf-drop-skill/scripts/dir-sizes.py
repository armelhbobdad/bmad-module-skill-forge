#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Deterministic directory-size measurement for skf-drop-skill.

The drop workflow twice needs an exact recursive byte total plus a stable
human label ("4.2 MB" / "812 KB"): select.md §9b renders the blast-radius
line ahead of the confirmation gate, and execute.md §4 reports the canonical
`disk_freed`. Summing file sizes and rounding a unit in the prompt has one
correct answer per input, so it belongs here — identical input yields
identical output, and the gate preview and the post-purge report agree on the
method (they can still differ only because they read at different times).

Two operations:

  sizes  <path>...      recursive byte size of each path (best-effort: a
                        non-existent path reports exists=false, bytes=0 and is
                        excluded from the total). Symlinks are measured by the
                        size of the link itself, never followed.
  humanize <bytes>...   sum a set of already-measured byte counts and format
                        one human label. execute.md §4 feeds it the sizes of
                        the paths that were actually deleted.

Output is a single JSON object on stdout. Exit codes: 0 ok; 2 usage error
(missing/unknown op, or a non-integer byte count for `humanize`).
"""
from __future__ import annotations

import json
import os
import sys

# 1024-based, matching the `du -h` feel the step files reference. Labelled
# KB/MB for readability; the raw integer total travels alongside for any
# consumer that needs exact arithmetic.
_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


def humanize_bytes(n: int) -> str:
    size = float(n)
    for unit in _UNITS:
        if size < 1024 or unit == _UNITS[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{int(n)} B"  # unreachable; keeps type checkers happy


def dir_bytes(path: str) -> int:
    """Recursive byte size of a file, directory, or symlink (link not followed)."""
    if os.path.islink(path):
        return os.lstat(path).st_size
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = os.path.join(root, name)
            try:
                total += os.lstat(fp).st_size
            except OSError:
                pass
    return total


def _op_sizes(paths: list[str]) -> dict:
    entries = []
    total = 0
    for p in paths:
        exists = os.path.exists(p) or os.path.islink(p)
        b = dir_bytes(p) if exists else 0
        if exists:
            total += b
        entries.append({"path": p, "exists": exists, "bytes": b, "human": humanize_bytes(b)})
    return {
        "status": "ok",
        "op": "sizes",
        "paths": entries,
        "total_bytes": total,
        "total_human": humanize_bytes(total),
    }


def _op_humanize(raw: list[str]) -> dict:
    total = 0
    for value in raw:
        try:
            total += int(value)
        except (TypeError, ValueError):
            print(
                json.dumps({"status": "error", "error": f"not an integer byte count: {value!r}"}),
                file=sys.stderr,
            )
            sys.exit(2)
    return {"status": "ok", "op": "humanize", "total_bytes": total, "total_human": humanize_bytes(total)}


def main(argv: list[str]) -> int:
    if not argv:
        print(json.dumps({"status": "error", "error": "usage: dir-sizes.py {sizes|humanize} <args>"}), file=sys.stderr)
        return 2
    op, args = argv[0], argv[1:]
    if op == "sizes":
        print(json.dumps(_op_sizes(args)))
        return 0
    if op == "humanize":
        print(json.dumps(_op_humanize(args)))
        return 0
    print(json.dumps({"status": "error", "error": f"unknown op: {op!r}"}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
