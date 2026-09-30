#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Print the stdin payload of a shared SKF helper, read from the files on disk.

coverage-check.md runs two shared helpers that take one JSON payload on
stdin and read no file themselves: skf-detect-workspaces.py (§0b: is the
local source a monorepo?) and skf-extract-public-api.py --mode quick (§2:
the Quick-tier export scan). A payload the model writes by hand can cut a
source file short or escape it wrongly, and the helper then fails or answers
for the wrong text. This script reads the files and prints the payload, and
the step pipes it into the helper:

  uv run stage-helper-payload.py detect-workspaces --source-root <dir> \\
      | uv run skf-detect-workspaces.py
  uv run stage-helper-payload.py extract-public-api --source-root <dir> \\
      --language <language> [--manifest <path>] --entry <path> [--entry <path> ...] \\
      | uv run skf-extract-public-api.py --mode quick

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

extract-public-api prints {"language": ..., "manifest": {"path", "content"},
"entries": [{"path", "content"}, ...], "mode": "quick"}: each path as
given, relative to --source-root and written with "/", and each content the
file's text (UTF-8, a leading byte order mark dropped). An entry given twice
is read once. Without --manifest, the manifest is {"path": "", "content": ""}
and the helper reports no package metadata. --language is passed through
unchecked: the helper exits 1 on a language it does not parse.

The payload is one line of ASCII JSON on stdout, so a pipe carries the same
bytes on every platform.

Exit codes:
  0  the payload is printed
  1  --source-root is not a folder, or a --manifest or --entry path is
     absolute, leads outside --source-root, or names no file; one JSON line
     {"status": "error", "error": ...} goes to stderr and nothing to stdout,
     so the helper the payload was piped into reads no input and fails too
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


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig", errors="replace")


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
# extract-public-api
# --------------------------------------------------------------------------


def _member(root: Path, value: str, flag: str) -> tuple[str, Path]:
    """The POSIX path as given and the file it names, which must lie inside `root`."""
    if Path(value).is_absolute():
        raise StageError(f"{flag} must be relative to --source-root: {value}")
    path = root / value
    if not path.resolve().is_relative_to(root.resolve()):
        raise StageError(f"{flag} leads outside --source-root: {value}")
    if not path.is_file():
        raise StageError(f"{flag} names no file under --source-root: {value}")
    return Path(value).as_posix(), path


def public_api_payload(source_root: str, language: str, manifest: str | None, entries: list[str]) -> dict:
    root = _source_root(source_root)
    out = {"language": language, "manifest": {"path": "", "content": ""}, "entries": [], "mode": "quick"}
    if manifest is not None:
        rel, path = _member(root, manifest, "--manifest")
        out["manifest"] = {"path": rel, "content": _read_text(path)}
    seen = set()
    for value in entries:
        rel, path = _member(root, value, "--entry")
        if rel in seen:
            continue
        seen.add(rel)
        out["entries"].append({"path": rel, "content": _read_text(path)})
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_detect_workspaces(args: argparse.Namespace) -> dict:
    return workspaces_payload(args.source_root)


def _cmd_extract_public_api(args: argparse.Namespace) -> dict:
    return public_api_payload(args.source_root, args.language, args.manifest, args.entry)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stage-helper-payload",
        description="Print a shared helper's stdin payload, read from the files on disk.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("detect-workspaces", help="the tree and root files for skf-detect-workspaces.py")
    p.add_argument("--source-root", required=True, help="the local source folder")
    p.set_defaults(func=_cmd_detect_workspaces)

    p = sub.add_parser("extract-public-api",
                       help="the manifest and entry files for skf-extract-public-api.py --mode quick")
    p.add_argument("--source-root", required=True, help="the local source folder")
    p.add_argument("--language", required=True, help="passed through to the helper")
    p.add_argument("--manifest", help="the package manifest, relative to --source-root")
    p.add_argument("--entry", action="append", required=True,
                   help="an entry-point file, relative to --source-root (repeatable)")
    p.set_defaults(func=_cmd_extract_public_api)

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
