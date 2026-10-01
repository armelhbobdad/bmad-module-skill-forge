#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Print the stdin payload of a shared SKF helper, read from the files on disk.

coverage-check.md §0b runs skf-detect-workspaces.py (is the local source a
monorepo?), a shared helper that takes one JSON payload on stdin and reads
no file itself. A payload the model writes by hand can cut a file short or
escape it wrongly, and the helper then fails or answers for the wrong text.
This script reads the files and prints the payload, and the step pipes it
into the helper:

  uv run stage-helper-payload.py detect-workspaces --source-root <dir> \\
      | uv run skf-detect-workspaces.py

(The Quick-tier export scan needs no payload: skf-extract-public-api.py
--mode quick reads its files itself, with --manifest-file and --entry-file.)

detect-workspaces prints {"tree": [...], "manifests": {...}}:

  tree       every file below --source-root, as a POSIX path relative to
             it, sorted. Folders named in SKIPPED_DIRS (installed
             dependencies, virtual environments, build output, caches) and
             hidden folders (a name that starts with ".") are not read, and a
             linked folder is not followed.
  manifests  the text of each file directly in --source-root that is not
             hidden, holds at most MAX_ROOT_FILE_BYTES and reads as UTF-8, by
             its name. The detector reads the root manifests it knows
             (package.json, pnpm-workspace.yaml, lerna.json, Cargo.toml ...)
             and ignores the rest, so this script keeps no list of their
             names to fall out of step with the detector's.

The payload is one line of ASCII JSON on stdout, so a pipe carries the same
bytes on every platform.

Exit codes:
  0  the payload is printed
  1  --source-root is not a folder; one JSON line {"status": "error",
     "error": ...} goes to stderr and nothing to stdout, so the helper the
     payload was piped into reads no input and fails too
  2  bad arguments (argparse: a missing or unknown argument, usage on stderr)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Folders that hold no workspace member of the repository itself.
SKIPPED_DIRS = frozenset({
    "node_modules", "bower_components", "jspm_packages", "vendor", "Pods",
    "venv", "site-packages", "__pycache__", "target",
})
MAX_ROOT_FILE_BYTES = 1024 * 1024


class StageError(Exception):
    """A path the payload cannot be built from."""


def _source_root(value: str) -> Path:
    root = Path(value)
    if not root.is_dir():
        raise StageError(f"--source-root is not a folder: {value}")
    return root


# --------------------------------------------------------------------------
# detect-workspaces
# --------------------------------------------------------------------------


def _skipped(name: str) -> bool:
    return name.startswith(".") or name in SKIPPED_DIRS


def list_tree(root: Path) -> list[str]:
    """Every file below `root` as a sorted POSIX path, outside skipped and linked folders."""
    tree = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not _skipped(d) and not (here / d).is_symlink()]
        for name in filenames:
            tree.append((here / name).relative_to(root).as_posix())
    return sorted(tree)


def root_texts(root: Path) -> dict[str, str]:
    """The text of each file directly in `root` that is not hidden, small enough, and UTF-8."""
    texts = {}
    for path in sorted(root.iterdir()):
        if path.name.startswith(".") or path.is_symlink() or not path.is_file():
            continue
        if path.stat().st_size > MAX_ROOT_FILE_BYTES:
            continue
        try:
            texts[path.name] = path.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError:
            continue
    return texts


def workspaces_payload(source_root: str) -> dict:
    root = _source_root(source_root)
    return {"tree": list_tree(root), "manifests": root_texts(root)}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_detect_workspaces(args: argparse.Namespace) -> dict:
    return workspaces_payload(args.source_root)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stage-helper-payload",
        description="Print a shared helper's stdin payload, read from the files on disk.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("detect-workspaces", help="the tree and root files for skf-detect-workspaces.py")
    p.add_argument("--source-root", required=True, help="the local source folder")
    p.set_defaults(func=_cmd_detect_workspaces)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        payload = args.func(args)
    except (StageError, OSError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
