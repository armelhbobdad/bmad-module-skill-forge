# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF Detect Workspaces — pure detector for monorepo / multi-package layouts.

Takes a JSON payload on stdin describing a target repo's file tree plus the
contents of a small set of root manifests, and returns whether a workspace
layout is present, which manifest kind drives it, and the list of resolved
workspaces. The helper does NO file I/O — the caller (typically
skf-brief-skill step-02 §1b) fetches files via `gh api` / local filesystem
and pipes the relevant content in.

Detection runs in priority order; the first matching detector wins:

  1. npm-workspaces       package.json has `workspaces: [...]` or `{packages: [...]}`
  2. pnpm-workspaces      pnpm-workspace.yaml exists with a `packages:` list
  3. lerna                lerna.json exists (`packages` field optional, defaults to `packages/*`)
  4. cargo-workspace      Cargo.toml has `[workspace]` with `members = [...]`
  5. python-multi-package multiple pyproject.toml under packages/* or apps/*
  6. generic-folders      apps/, packages/, libs/, or code/ each with subdirs
                          containing a recognisable manifest

Glob members (`packages/*`, `apps/*`, etc.) are resolved against the supplied
file tree; only directories whose recognisable manifest is present in the tree
become workspaces. A detector that finds zero non-excluded matches falls
through to the next detector instead of returning is_monorepo: true with an
empty list.

Input JSON shape (stdin):

  {
    "tree": ["package.json", "packages/foo/package.json", "packages/foo/src/index.js", ...],
    "manifests": {
      "package.json":        "<raw text>",
      "Cargo.toml":          "<raw text>",
      "pnpm-workspace.yaml": "<raw text>",
      "lerna.json":          "<raw text>"
    }
  }

  - `tree` is a flat list of repository-relative file paths (POSIX separators).
    Per-workspace child manifests (e.g. `packages/foo/package.json`) MUST appear
    here for glob resolution; their contents are optional.
  - `manifests` is a dict keyed by repository-relative path; only root-level
    manifests must be supplied. Per-workspace manifest contents may be
    included to populate the workspace `name` field, but absence is fine
    (the path basename is used as a fallback).

Output JSON shape (stdout):

  {
    "is_monorepo":   true | false,
    "manifest_kind": "npm-workspaces" | "pnpm-workspaces" | "lerna"
                   | "cargo-workspace" | "python-multi-package"
                   | "generic-folders" | null,
    "workspaces":    [
      {"name": "foo", "path": "packages/foo", "manifest": "packages/foo/package.json"},
      ...
    ],
    "warnings":      ["..."]
  }

Exit codes:

  0  success (regardless of is_monorepo value)
  1  payload error (malformed top-level JSON shape)
  2  stdin / argparse / JSON-decode error
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import tomllib
from typing import Optional


GENERIC_PARENTS = ("apps", "packages", "libs", "code")
RECOGNISED_MANIFESTS = (
    "package.json",
    "Cargo.toml",
    "pyproject.toml",
    "setup.py",
    "go.mod",
    "build.gradle",
    "build.gradle.kts",
    "pom.xml",
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _normalise_path(path: str) -> str:
    """Strip leading './' and trailing '/' so comparisons are stable."""
    while path.startswith("./"):
        path = path[2:]
    return path.rstrip("/")


def _match_globs(tree: set[str], globs: list[str]) -> list[str]:
    """Resolve workspace globs against the tree.

    Returns the sorted list of *directory paths* that have at least one matching
    manifest under them. Patterns starting with `!` are exclusions applied after
    the inclusion pass. Brace expansion is not supported (npm/pnpm rarely use
    it in published configs); a literal pattern without `*` is treated as a
    literal directory path.
    """
    includes: list[str] = []
    excludes: list[str] = []
    for raw in globs:
        if not isinstance(raw, str) or not raw.strip():
            continue
        cleaned = _normalise_path(raw.strip())
        if cleaned.startswith("!"):
            excludes.append(cleaned[1:])
        else:
            includes.append(cleaned)

    candidate_dirs: set[str] = set()
    for pat in includes:
        if "*" in pat:
            for path in tree:
                # match the directory portion of every file path against the glob
                parts = path.split("/")
                for depth in range(1, len(parts)):
                    candidate = "/".join(parts[:depth])
                    if fnmatch.fnmatchcase(candidate, pat):
                        candidate_dirs.add(candidate)
        else:
            # literal directory; include only if the tree contains a manifest under it
            candidate_dirs.add(pat)

    # Apply excludes
    survivors: set[str] = set()
    for cand in candidate_dirs:
        if any(fnmatch.fnmatchcase(cand, ex) or cand == ex for ex in excludes):
            continue
        survivors.add(cand)

    return sorted(survivors)


def _find_workspace_manifest(workspace_path: str, tree: set[str]) -> Optional[str]:
    """Return the first recognised manifest under `workspace_path`, or None."""
    for manifest in RECOGNISED_MANIFESTS:
        candidate = f"{workspace_path}/{manifest}"
        if candidate in tree:
            return candidate
    return None


def _read_workspace_name(manifest_path: str, manifests: dict[str, str], fallback: str) -> str:
    """Extract a sensible name from a workspace's manifest.

    Best-effort: returns the manifest's declared package name when parseable,
    otherwise the directory basename.
    """
    content = manifests.get(manifest_path)
    if content is None:
        return fallback
    if manifest_path.endswith("package.json"):
        try:
            data = json.loads(content)
            name = data.get("name")
            if isinstance(name, str) and name:
                return name
        except (json.JSONDecodeError, AttributeError):
            pass
    elif manifest_path.endswith("Cargo.toml"):
        try:
            data = tomllib.loads(content)
            name = data.get("package", {}).get("name")
            if isinstance(name, str) and name:
                return name
        except tomllib.TOMLDecodeError:
            pass
    elif manifest_path.endswith("pyproject.toml"):
        try:
            data = tomllib.loads(content)
            name = data.get("project", {}).get("name")
            if isinstance(name, str) and name:
                return name
        except tomllib.TOMLDecodeError:
            pass
    return fallback


def _build_workspaces(
    workspace_dirs: list[str],
    tree: set[str],
    manifests: dict[str, str],
) -> list[dict]:
    """Resolve each workspace dir to its manifest + name, drop dirs without a manifest."""
    out: list[dict] = []
    for ws_path in workspace_dirs:
        manifest = _find_workspace_manifest(ws_path, tree)
        if manifest is None:
            continue
        fallback_name = ws_path.rsplit("/", 1)[-1] or ws_path
        name = _read_workspace_name(manifest, manifests, fallback_name)
        out.append({"name": name, "path": ws_path, "manifest": manifest})
    return out


# --------------------------------------------------------------------------
# Detectors
# --------------------------------------------------------------------------


def detect_npm_workspaces(
    tree: set[str], manifests: dict[str, str], warnings: list[str]
) -> Optional[list[dict]]:
    content = manifests.get("package.json")
    if content is None:
        return None
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        warnings.append(f"package.json JSON parse error: {e}")
        return None
    if not isinstance(data, dict):
        return None
    ws = data.get("workspaces")
    if ws is None:
        return None
    if isinstance(ws, dict):
        ws = ws.get("packages", [])
    if not isinstance(ws, list) or not ws:
        return None
    dirs = _match_globs(tree, ws)
    return _build_workspaces(dirs, tree, manifests)


def detect_pnpm_workspaces(
    tree: set[str], manifests: dict[str, str], warnings: list[str]
) -> Optional[list[dict]]:
    content = manifests.get("pnpm-workspace.yaml")
    if content is None:
        return None
    try:
        import yaml  # local import keeps top-level cheap when YAML is unused
    except ImportError:
        warnings.append("pyyaml not available — pnpm-workspace.yaml not parsed")
        return None
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        warnings.append(f"pnpm-workspace.yaml parse error: {e}")
        return None
    if not isinstance(data, dict):
        return None
    pkgs = data.get("packages")
    if not isinstance(pkgs, list) or not pkgs:
        return None
    dirs = _match_globs(tree, pkgs)
    return _build_workspaces(dirs, tree, manifests)


def detect_lerna(
    tree: set[str], manifests: dict[str, str], warnings: list[str]
) -> Optional[list[dict]]:
    content = manifests.get("lerna.json")
    if content is None:
        return None
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        warnings.append(f"lerna.json JSON parse error: {e}")
        return None
    if not isinstance(data, dict):
        return None
    pkgs = data.get("packages", ["packages/*"])
    if not isinstance(pkgs, list):
        return None
    dirs = _match_globs(tree, pkgs)
    return _build_workspaces(dirs, tree, manifests)


def detect_cargo_workspace(
    tree: set[str], manifests: dict[str, str], warnings: list[str]
) -> Optional[list[dict]]:
    content = manifests.get("Cargo.toml")
    if content is None:
        return None
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as e:
        warnings.append(f"Cargo.toml parse error: {e}")
        return None
    workspace = data.get("workspace")
    if not isinstance(workspace, dict):
        return None
    members = workspace.get("members")
    if not isinstance(members, list) or not members:
        return None
    excludes = workspace.get("exclude", [])
    patterns = list(members) + [f"!{e}" for e in excludes if isinstance(e, str)]
    dirs = _match_globs(tree, patterns)
    return _build_workspaces(dirs, tree, manifests)


def detect_python_multi_package(
    tree: set[str], manifests: dict[str, str], warnings: list[str]
) -> Optional[list[dict]]:
    candidates: list[str] = []
    for path in tree:
        if not path.endswith("/pyproject.toml"):
            continue
        parent = path[: -len("/pyproject.toml")]
        # match `packages/<x>/pyproject.toml` or `apps/<x>/pyproject.toml`
        if re.match(r"^(packages|apps)/[^/]+$", parent):
            candidates.append(parent)
    if len(candidates) < 2:
        return None
    return _build_workspaces(sorted(set(candidates)), tree, manifests)


def detect_generic_folders(
    tree: set[str], manifests: dict[str, str], warnings: list[str]
) -> Optional[list[dict]]:
    """Last-resort: a top-level apps/ or packages/ or libs/ or code/ with subdirs."""
    discovered: list[str] = []
    for parent in GENERIC_PARENTS:
        children: set[str] = set()
        for path in tree:
            if not path.startswith(parent + "/"):
                continue
            parts = path.split("/")
            if len(parts) < 3:
                continue  # need at least parent/child/file
            children.add(f"{parent}/{parts[1]}")
        for child in children:
            if _find_workspace_manifest(child, tree) is not None:
                discovered.append(child)
        if len(discovered) >= 2:
            # Stick with the first parent that yields ≥2 manifested children
            break
        discovered = []
    if len(discovered) < 2:
        return None
    return _build_workspaces(sorted(set(discovered)), tree, manifests)


DETECTORS: list[tuple[str, callable]] = [
    ("npm-workspaces",       detect_npm_workspaces),
    ("pnpm-workspaces",      detect_pnpm_workspaces),
    ("lerna",                detect_lerna),
    ("cargo-workspace",      detect_cargo_workspace),
    ("python-multi-package", detect_python_multi_package),
    ("generic-folders",      detect_generic_folders),
]


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def detect(payload: dict) -> dict:
    """Pure detection — the CLI wraps this with stdin/stdout I/O and exit-code mapping."""
    tree_raw = payload.get("tree")
    manifests = payload.get("manifests")
    warnings: list[str] = []
    if not isinstance(tree_raw, list):
        return {"_payload_error": "missing or non-list 'tree' field"}
    if not isinstance(manifests, dict):
        return {"_payload_error": "missing or non-dict 'manifests' field"}
    tree: set[str] = {_normalise_path(p) for p in tree_raw if isinstance(p, str) and p.strip()}

    for kind, detector in DETECTORS:
        result = detector(tree, manifests, warnings)
        if result and len(result) >= 1:
            return {
                "is_monorepo":   True,
                "manifest_kind": kind,
                "workspaces":    result,
                "warnings":      warnings,
            }

    return {
        "is_monorepo":   False,
        "manifest_kind": None,
        "workspaces":    [],
        "warnings":      warnings,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Detect monorepo / workspace layouts from a tree + manifests payload.")
    parser.add_argument("--json", help="Inline JSON payload (otherwise read from stdin).")
    args = parser.parse_args(argv)

    raw = args.json
    if raw is None:
        raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"error": "empty input"}), file=sys.stderr)
        return 2

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"json decode error: {e}"}), file=sys.stderr)
        return 2

    result = detect(payload)
    if "_payload_error" in result:
        print(json.dumps({"error": result["_payload_error"]}), file=sys.stderr)
        return 1

    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
