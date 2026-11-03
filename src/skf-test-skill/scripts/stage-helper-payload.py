#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Print the stdin payload of a shared SKF helper, read from the files on disk.

coverage-check.md §0b runs skf-detect-workspaces.py (is the local source a
monorepo?), a shared helper that takes one JSON payload on stdin and reads
no file itself. A payload the model writes by hand can cut a file short or
escape it wrongly, and the helper then fails or answers for the wrong text.
This script reads the files and prints the payload, and the step pipes it
into the helper:

  uv run stage-helper-payload.py detect-workspaces --source-root <dir> \\
      [--brief <skill-brief.yaml>] | uv run skf-detect-workspaces.py

(The Quick-tier export scan needs no payload: skf-extract-public-api.py
--mode quick reads its files itself, with --manifest-file and --entry-file.)

detect-workspaces prints {"tree": [...], "manifests": {...}}:

  tree       every file below --source-root, as a POSIX path relative to
             it, sorted. Folders named in SKIPPED_DIRS (installed
             dependencies, virtual environments, build output, caches) and
             hidden folders (a name that starts with ".") are not read, and a
             linked folder is not followed. With --brief, the tree is the
             detector's scoped_tree of it under the brief's scope.exclude
             globs (#780): a workspace member counts only through the files
             the brief keeps, so excluding a member's source files drops it,
             excluding only its manifest does not, every root manifest
             stays, and a workspace with no member left is no workspace.
  manifests  the text of each file directly in --source-root that is not
             hidden, holds at most MAX_ROOT_FILE_BYTES and reads as UTF-8, by
             its name, whatever the brief excludes. The detector reads the
             root manifests it knows (package.json, pnpm-workspace.yaml,
             lerna.json, Cargo.toml ...) and ignores the rest, so this script
             keeps no list of their names to fall out of step with the
             detector's.

--brief reads the brief with load-coverage-inputs.py's read_brief (the
script beside this one, which loads skf-resolve-authoritative-files.py's
parse_brief_yaml from the shared scripts folder), and matches each
scope.exclude glob by its glob_match, skf-resolve-authoritative-files.py's
rule (`**` spans any number of path segments, none included; `*` and `?`
stay inside one), the rule skf-extract-public-api.py applies to the same
brief. skf-detect-workspaces.py's scoped_tree, loaded from the shared
scripts folder (SHARED_SCRIPTS), keeps the paths: the monorepo arm of
skf-extract-public-api.py reads the same function.

The payload is one line of ASCII JSON on stdout, so a pipe carries the same
bytes on every platform.

Exit codes:
  0  the payload is printed
  1  --source-root is not a folder, or --brief cannot be read (missing, not
     UTF-8, not YAML, a value YAML cannot build such as an invalid date, not
     a mapping, PyYAML not installed) or a script it loads is missing; one
     JSON line {"status": "error", "error": ...} goes to stderr and nothing
     to stdout, so the helper the payload was piped into reads no input and
     fails too
  2  bad arguments (argparse: a missing or unknown argument, usage on stderr)
"""

from __future__ import annotations

import argparse
import importlib.util
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
SCRIPTS = Path(__file__).resolve().parent
# skf-detect-workspaces.py's folder, installed and in src/ alike.
SHARED_SCRIPTS = SCRIPTS.parent.parent / "shared" / "scripts"


class StageError(Exception):
    """A path the payload cannot be built from."""


def _source_root(value: str) -> Path:
    root = Path(value)
    if not root.is_dir():
        raise StageError(f"--source-root is not a folder: {value}")
    return root


def _load(folder: Path, filename: str):
    """A script in `folder`, loaded as a module, as load-coverage-inputs.py loads its siblings."""
    path = folder / filename
    spec = importlib.util.spec_from_file_location("skf_" + filename[:-3].replace("-", "_"), path)
    if spec is None or spec.loader is None or not path.is_file():
        raise StageError(f"{filename} not found in {folder}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scoped_tree(tree: list[str], brief: str) -> list[str]:
    """The paths of `tree` workspace detection reads under the brief at `brief`."""
    inputs = _load(SCRIPTS, "load-coverage-inputs.py")
    try:
        excludes = inputs.read_brief(brief)["scope"]["exclude"]
    except inputs.InputError as exc:
        raise StageError(str(exc)) from exc
    except ValueError as exc:  # a value YAML cannot build, such as an invalid date
        raise StageError(f"--brief {brief} is not valid YAML: {' '.join(str(exc).split())}") from exc
    return _load(SHARED_SCRIPTS, "skf-detect-workspaces.py").scoped_tree(tree, excludes, inputs.glob_match)


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


def workspaces_payload(source_root: str, brief: str | None = None) -> dict:
    """The tree (with `brief`, the part of it the brief keeps) and the root files."""
    root = _source_root(source_root)
    tree = list_tree(root)
    if brief is not None:
        tree = scoped_tree(tree, brief)
    return {"tree": tree, "manifests": root_texts(root)}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_detect_workspaces(args: argparse.Namespace) -> dict:
    return workspaces_payload(args.source_root, args.brief)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stage-helper-payload",
        description="Print a shared helper's stdin payload, read from the files on disk.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("detect-workspaces", help="the tree and root files for skf-detect-workspaces.py")
    p.add_argument("--source-root", required=True, help="the local source folder")
    p.add_argument("--brief", help="the skill brief, whose scope.exclude globs leave paths out of the tree")
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
