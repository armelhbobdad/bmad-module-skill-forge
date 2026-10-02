#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Deterministic directory-size measurement for skf-drop-skill.

The drop workflow twice needs a stable human label ("4.2 MB" / "812 KB"):
select.md section 9b renders the blast-radius line ahead of the confirmation
gate from the exact recursive byte total measured here, and execute.md
section 4 formats the canonical `disk_freed` from the `bytes_freed` that
skf-skill-inventory.py guarded-delete measured just before it deleted each
folder. Summing file sizes and rounding a unit in the prompt has one correct
answer per input, so it belongs here: identical input yields identical
output, and the gate preview and the post-purge report agree on the method
(they can still differ only because they read at different times).

Two operations:

  sizes  <path>...      recursive byte size of each path (best-effort: a
                        non-existent path reports exists=false, bytes=0 and is
                        excluded from the total). Symlinks are measured by the
                        size of the link itself, never followed.
  humanize <bytes>...   sum a set of already-measured byte counts and format
                        one human label. execute.md section 4 feeds it the
                        `bytes_freed` of guarded-delete.

Output is a single JSON object on stdout. Exit codes: 0 ok (and --help);
2 usage error (missing/unknown op or argument, or a non-integer byte count
for `humanize`), reported as a JSON error on stderr.
"""
from __future__ import annotations

import argparse
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


class _JsonErrorParser(argparse.ArgumentParser):
    """Report a usage error as the same stderr JSON and exit 2 as a bad byte count.

    The subcommand parsers are made with this class too, so an unknown op or
    flag never reaches argparse's own plain-text usage.
    """

    def error(self, message: str) -> None:
        print(json.dumps({"status": "error", "error": f"usage error: {self.prog}: {message}"}), file=sys.stderr)
        sys.exit(2)


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonErrorParser(
        prog="dir-sizes.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="op", required=True, metavar="{sizes,humanize}")

    p_sizes = sub.add_parser("sizes", help="recursive byte size of each path, and their total")
    p_sizes.add_argument("paths", nargs="*", metavar="path",
                         help="a file or folder to measure; a link is measured as itself, never followed")

    p_humanize = sub.add_parser("humanize", help="sum already-measured byte counts into one human label")
    p_humanize.add_argument("byte_counts", nargs="*", metavar="bytes",
                            help="an integer byte count, such as guarded-delete's bytes_freed")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.op == "sizes":
        print(json.dumps(_op_sizes(args.paths)))
    else:
        print(json.dumps(_op_humanize(args.byte_counts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
