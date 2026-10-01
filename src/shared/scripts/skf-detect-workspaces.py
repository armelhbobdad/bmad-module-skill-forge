# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF Detect Workspaces — pure detector for monorepo / multi-package layouts.

Takes a target repo's file tree plus the contents of a small set of root
manifests, and returns whether a workspace layout is present, which manifest
kind drives it, and the list of resolved workspaces. detect() does no file
I/O: the CLI reads the tree and the manifests from a JSON payload (stdin or
--json), or from the files --tree-file and --manifest-dir name, so a caller
(skf-brief-skill step 2 §1b, skf-test-skill's coverage check) can stage them
instead of typing a tree or a manifest into a shell string. With --snapshot
it prints the facts the tree gives an analysis instead (see "Tree snapshot"
below).

Detection runs in priority order; the first matching detector wins:

  1. npm-workspaces       package.json has `workspaces: [...]` or `{packages: [...]}`
  2. pnpm-workspaces      pnpm-workspace.yaml exists with a `packages:` list
  3. lerna                lerna.json exists (`packages` field optional, defaults to `packages/*`)
  4. rush                 rush.json lists `projects[]` (JSON with comments; its
                          content must be supplied under `manifests`)
  5. nx                   nx.json at the root, and folders holding a project.json
  6. cargo-workspace      Cargo.toml has `[workspace]` with `members = [...]`
  7. python-multi-package multiple pyproject.toml under packages/* or apps/*
  8. generic-folders      apps/, packages/, libs/, or code/ each with subdirs
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
      "lerna.json":          "<raw text>",
      "rush.json":           "<raw text>",
      "nx.json":             "<raw text>"
    }
  }

  - `tree` is a flat list of repository-relative file paths (POSIX separators).
    Per-workspace child manifests (e.g. `packages/foo/package.json`) MUST appear
    here for glob resolution; their contents are optional.
  - `manifests` is a dict keyed by repository-relative path; only root-level
    manifests must be supplied (nx.json may be left out when the tree lists
    it). Per-workspace manifest contents may be included to populate the
    workspace `name` field, but absence is fine (the path basename is used
    as a fallback); for Nx that is each project.json, for Rush the
    `packageName` in rush.json names each project.

Output JSON shape (stdout):

  {
    "is_monorepo":   true | false,
    "manifest_kind": "npm-workspaces" | "pnpm-workspaces" | "lerna"
                   | "rush" | "nx" | "cargo-workspace"
                   | "python-multi-package" | "generic-folders" | null,
    "workspaces":    [
      {"name": "foo", "path": "packages/foo", "manifest": "packages/foo/package.json"},
      ...
    ],
    "warnings":      ["..."]
  }

`warnings` also names each root manifest whose content a detector reads
(CONTENT_MANIFESTS) that the tree lists but `manifests` does not hold: the
detector that needs it cannot run, so a workspace layout it would find is
missed.

CLI:
  uv run skf-detect-workspaces.py < payload.json
  uv run skf-detect-workspaces.py --json '{"tree": [...], "manifests": {...}}'
  uv run skf-detect-workspaces.py --tree-file <file> --manifest-files
  uv run skf-detect-workspaces.py --tree-file <file> [--manifest-dir <dir>]
  uv run skf-detect-workspaces.py --tree-file <file> [--manifest-dir <dir>] \\
      --snapshot [--root <folder>]

--tree-file reads the tree from a file (`-` reads it from stdin) through
skf-detect-language.py's read_tree_file() (the sibling in this folder, which
must sit beside this script), whose --tree-file text lists the listings it
reads; one that holds no path is refused. With --tree-file, stdin is never
read for the payload: `manifests` comes with --json or --manifest-dir, or is
empty, and the payload may not carry `tree` as well. When the listing says
it was cut short (a GitHub tree's `truncated`), `warnings` says so: a
workspace whose manifest the listing lacks is not found.

--manifest-files prints the root manifests the --tree-file listing holds
whose content a detector reads (CONTENT_MANIFESTS), one repo path per line
with LF endings on every platform (nothing when there are none), and exits:
a shell loop fetches exactly those files into the folder --manifest-dir then
reads.

--manifest-dir reads `manifests` from a folder laid out like the repository,
a local checkout or the folder the --manifest-files paths were fetched into:
each root manifest of CONTENT_MANIFESTS the tree lists, then the manifest of
each workspace found, which names it. A file missing there, larger than
MAX_MANIFEST_BYTES or not UTF-8 was not supplied. Passing `manifests` in the
payload as well is an error.

Tree snapshot (--snapshot)
--------------------------

The facts an analysis of the repository, or of one folder of it (--root,
such as a workspace path), reads from the tree, counted by the script so no
caller counts or samples a long listing by hand. It takes the same inputs:

  {
    "root":                "" | "<folder>",  the folder described ("" for
                                             the repository)
    "truncated":           bool,   the --tree-file listing says it was cut
                                   short (a GitHub tree's `truncated`); the
                                   counts are then lower bounds, and a
                                   workspace may be missed
    "file_count":          N,      files under the root
    "source_file_count":   N,      of those, the source files: the
                                   extensions skf-detect-language.py's
                                   extension-frequency rule counts
    "dir_count":           N,      folders under the root
    "top_level_files":     [...],  names of the files directly in the root
    "top_level_dirs":      [...],  names of the folders directly in the root
    "manifest_kind":       the workspace layout the detectors find at the
                           repository root (null without one, and with
                           --root)
    "workspaces":          [...],  its workspaces, as detection lists them
    "module_root":         "" | "<folder>",  where the module candidates are
    "module_candidates":   [{"path": "<folder>", "file_count": N,
                             "source_file_count": N}, ...],  each folder
                                   directly in module_root but hidden ones,
                                   with the files and source files under it
    "registry_candidates": [...],  repo paths of the component registry
                                   files under the root
    "warnings":            [...]   the detection warnings at the repository
                                   root
  }

Modules. Which folders are the modules is the caller's judgment, so the
snapshot names none: it lists the candidates and what they hold. The module
root is the root's `src/` folder, else its `lib/` folder, else the root
itself, followed down while it holds no file and exactly one folder (hidden
ones and NON_MODULE_DIRS aside) that holds folders of its own (a Python
`src/<package>/` layout, or Java's `src/main/java/com/acme/`). The modules
are the workspaces when the detectors find some, else the candidates that
hold the library's own code (a folder with no source file, or of tests,
docs, examples, scripts, build tooling or CI, is none); a candidate that
holds most of the source files is the package itself (pandas/ at the root of
pandas), and a snapshot with --root <it> lists its own candidates. The count
of the modules picked is skf-recommend-scope-type.py's `module_count` input.

Registry candidates are the files the component-registry rule of
skf-recommend-scope-type.py reads (registry.ts, components.ts and their .tsx
forms, at any depth), found by that script's own rule (the sibling in this
folder, which must sit beside this script).

Exit codes:

  0  success (regardless of is_monorepo value)
  1  payload error (malformed top-level JSON shape)
  2  input error: empty stdin, invalid JSON, a bad or conflicting flag
     (argparse), the tree or the manifests passed twice, a tree listing that
     cannot be read, holds no path or reports a failure, a sibling script that
     cannot be loaded, or a --root under which the tree lists no file
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import posixpath
import re
import sys
import tomllib
from pathlib import Path
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
# Root manifests whose content a detector reads (nx.json counts by its place
# in the tree alone): --manifest-files lists them, --manifest-dir reads them,
# and a warning names each one the tree lists that was not supplied.
CONTENT_MANIFESTS = ("package.json", "pnpm-workspace.yaml", "lerna.json", "rush.json", "Cargo.toml")
MAX_MANIFEST_BYTES = 1024 * 1024
# Folders a snapshot's module root is never followed down through (names
# matched in lower case): tests, test helpers and fixtures, docs and sites,
# examples, playgrounds and benchmarks, build output, vendored dependencies
# and caches, and non-code resources. They still appear among the module
# candidates, with what they hold: which folders are modules is the
# caller's judgment.
NON_MODULE_DIRS = frozenset({
    "test", "tests", "__tests__", "testing", "spec", "specs", "testdata", "fixture", "fixtures", "e2e",
    "test-utils", "test_utils", "testutils", "__testutils__",
    "doc", "docs", "website", "www", "example", "examples", "demo", "demos", "sample", "samples",
    "playground", "playgrounds", "bench", "benches", "benchmark", "benchmarks", "scripts",
    "build", "dist", "out", "target", "coverage", "node_modules", "vendor", "__pycache__",
    "resources",
})


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
    pkgs = data.get("packages")
    if pkgs is None:
        return None
    if not isinstance(pkgs, list) or not pkgs:
        return None
    dirs = _match_globs(tree, pkgs)
    return _build_workspaces(dirs, tree, manifests)


def _strip_json_comments(content: str) -> str:
    """JSON with `//` and `/* */` comments and trailing commas (rush.json is
    JSONC) made plain JSON; string contents are left alone."""
    n = len(content)

    def comment_end(i: int) -> Optional[int]:
        """The index just past the comment that starts at `i`, or None."""
        if content.startswith("//", i):
            end = content.find("\n", i)
            return n if end < 0 else end
        if content.startswith("/*", i):
            end = content.find("*/", i + 2)
            return n if end < 0 else end + 2
        return None

    def next_token(i: int) -> str:
        """The first character at or after `i` outside blanks and comments."""
        while i < n:
            end = comment_end(i)
            if end is not None:
                i = end
            elif content[i].isspace():
                i += 1
            else:
                return content[i]
        return ""

    out: list[str] = []
    i = 0
    while i < n:
        ch = content[i]
        end = comment_end(i)
        if ch == '"':
            j = i + 1
            while j < n and content[j] != '"':
                j += 2 if content[j] == "\\" else 1
            out.append(content[i : j + 1])
            i = j + 1
        elif end is not None:
            i = end
        else:
            # a comma before the closing bracket of its list or object goes
            if not (ch == "," and next_token(i + 1) in ("}", "]")):
                out.append(ch)
            i += 1
    return "".join(out)


def detect_rush(
    tree: set[str], manifests: dict[str, str], warnings: list[str]
) -> Optional[list[dict]]:
    """Rush: rush.json's `projects[]`, each a `projectFolder` with a
    package.json in the tree, named by its `packageName`. A rush.json the
    tree lists without its content is named in detect()'s warnings."""
    content = manifests.get("rush.json")
    if content is None:
        return None
    try:
        data = json.loads(_strip_json_comments(content))
    except json.JSONDecodeError as e:
        warnings.append(f"rush.json JSON parse error: {e}")
        return None
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, list):
        return None
    out: list[dict] = []
    seen: set[str] = set()
    for project in projects:
        if not isinstance(project, dict) or not isinstance(project.get("projectFolder"), str):
            continue
        folder = _normalise_path(project["projectFolder"].strip())
        manifest = f"{folder}/package.json"
        if not folder or folder in seen or manifest not in tree:
            continue
        seen.add(folder)
        name = project.get("packageName")
        if not isinstance(name, str) or not name:
            name = _read_workspace_name(manifest, manifests, folder.rsplit("/", 1)[-1])
        out.append({"name": name, "path": folder, "manifest": manifest})
    return sorted(out, key=lambda ws: ws["path"])


def detect_nx(
    tree: set[str], manifests: dict[str, str], warnings: list[str]
) -> Optional[list[dict]]:
    """Nx: with nx.json at the root, each folder below it holding a
    project.json is a project, named by that file's `name` when its
    content is supplied. An Nx repository that declares its projects
    through package.json workspaces is found by the npm or pnpm detector."""
    if "nx.json" not in tree and "nx.json" not in manifests:
        return None
    out: list[dict] = []
    for path in sorted(tree):
        if not path.endswith("/project.json"):
            continue
        folder = path[: -len("/project.json")]
        if "node_modules" in folder.split("/"):
            continue
        name = folder.rsplit("/", 1)[-1]
        content = manifests.get(path)
        if content is not None:
            try:
                declared = json.loads(content).get("name")
            except (json.JSONDecodeError, AttributeError):
                declared = None
            if isinstance(declared, str) and declared:
                name = declared
        out.append({"name": name, "path": folder, "manifest": path})
    return out


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
        # match `packages/<x>/pyproject.toml`, `apps/<x>/pyproject.toml`, or `libs/<x>/pyproject.toml`
        if re.match(r"^(packages|apps|libs)/[^/]+$", parent):
            candidates.append(parent)
    if len(candidates) < 2:
        return None
    return _build_workspaces(sorted(set(candidates)), tree, manifests)


def detect_generic_folders(
    tree: set[str], manifests: dict[str, str], warnings: list[str]
) -> Optional[list[dict]]:
    """Last-resort: ≥2 manifested subdirs under any combination of apps/, packages/, libs/, code/.

    Accumulates across all GENERIC_PARENTS — a repo with one manifested child under apps/
    and one under packages/ counts as a 2-workspace monorepo. Earlier detectors (npm, pnpm,
    cargo) take priority for repos with a root workspace manifest.
    """
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
    if len(discovered) < 2:
        return None
    return _build_workspaces(sorted(set(discovered)), tree, manifests)


DETECTORS: list[tuple[str, callable]] = [
    ("npm-workspaces",       detect_npm_workspaces),
    ("pnpm-workspaces",      detect_pnpm_workspaces),
    ("lerna",                detect_lerna),
    ("rush",                 detect_rush),
    ("nx",                   detect_nx),
    ("cargo-workspace",      detect_cargo_workspace),
    ("python-multi-package", detect_python_multi_package),
    ("generic-folders",      detect_generic_folders),
]

# Language ecosystem each manifest kind belongs to. Drives the cross-ecosystem
# secondary-manifest warning below. `generic-folders` is intentionally absent —
# it is a tree-shape heuristic, not a distinct root workspace manifest, so it
# never participates in cross-ecosystem warnings.
ECOSYSTEM_OF_KIND = {
    "npm-workspaces":       "js",
    "pnpm-workspaces":      "js",
    "lerna":                "js",
    "rush":                 "js",
    "nx":                   "js",
    "cargo-workspace":      "rust",
    "python-multi-package": "python",
}

ROOT_MANIFEST_OF_KIND = {
    "npm-workspaces":       "package.json",
    "pnpm-workspaces":      "pnpm-workspace.yaml",
    "lerna":                "lerna.json",
    "rush":                 "rush.json",
    "nx":                   "nx.json",
    "cargo-workspace":      "Cargo.toml",
    "python-multi-package": None,  # discovered from the tree; no single root manifest
}


def _cross_ecosystem_warnings(
    primary_kind: str, tree: set[str], manifests: dict[str, str]
) -> list[str]:
    """Warn when a root workspace manifest from a *different* language ecosystem
    than the surfaced one also resolves members.

    First-match-wins detection silently drops a co-located workspace from another
    ecosystem (e.g. a root `Cargo.toml [workspace]` when a pnpm workspace wins),
    which then poisons downstream language detection and the §1b workspace menu.
    This re-runs only the manifest-backed detectors from a different ecosystem,
    against a throwaway warnings sink so their parse errors are not propagated,
    and emits one warning per ignored cross-ecosystem kind that resolves >=1
    member. The surfaced `manifest_kind` / `workspaces` are left unchanged.
    """
    primary_eco = ECOSYSTEM_OF_KIND.get(primary_kind)
    out: list[str] = []
    for kind, detector in DETECTORS:
        eco = ECOSYSTEM_OF_KIND.get(kind)
        if kind == primary_kind or eco is None or eco == primary_eco:
            continue  # self, generic-folders, or same ecosystem as the winner
        result = detector(tree, manifests, [])
        if result and len(result) >= 1:
            manifest = ROOT_MANIFEST_OF_KIND.get(kind)
            where = f" (root {manifest})" if manifest else ""
            out.append(
                f"cross-ecosystem workspace ignored: {kind}{where} resolves "
                f"{len(result)} member(s) but only {primary_kind} was surfaced. "
                f"If the skill targets the {kind} ecosystem, re-scope to it — "
                f"language detection keys off the surfaced manifest_kind."
            )
    return out


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
    for name in CONTENT_MANIFESTS:
        if name in tree and name not in manifests:
            warnings.append(
                f"{name} is in the tree but its content was not supplied: pass it under manifests "
                "(or with --manifest-dir) so the detectors can read it"
            )

    for kind, detector in DETECTORS:
        result = detector(tree, manifests, warnings)
        if result and len(result) >= 1:
            warnings.extend(_cross_ecosystem_warnings(kind, tree, manifests))
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


# --------------------------------------------------------------------------
# Tree snapshot
# --------------------------------------------------------------------------


def _module_root(files: list[str], dirs: set[str]) -> str:
    """The folder whose own folders are a snapshot's module candidates,
    relative to the folder the snapshot describes: its `src/`, else its
    `lib/`, else the folder itself, followed down while it holds no file
    and exactly one folder (hidden ones and NON_MODULE_DIRS aside), which
    holds folders of its own (a wrapper such as a Python `src/<package>/`,
    never a lone `src/components/`)."""
    children: dict[str, list[str]] = {}
    for folder in dirs:
        name = posixpath.basename(folder)
        if not name.startswith(".") and name.lower() not in NON_MODULE_DIRS:
            children.setdefault(posixpath.dirname(folder), []).append(folder)
    holds_files = {posixpath.dirname(f) for f in files}
    base = next((d for d in ("src", "lib") if d in dirs), "")
    while True:
        found = children.get(base, [])
        if len(found) != 1 or base in holds_files or not children.get(found[0]):
            return base
        base = found[0]


def snapshot(tree: list, manifests: dict, root: str = "", truncated: bool = False) -> dict:
    """The facts the tree gives an analysis of `root` ("" for the
    repository): see "Tree snapshot" in the module docstring. Raises
    ValueError when the tree lists no file under a `root` given, and
    ImportError when skf-detect-language.py or skf-recommend-scope-type.py
    does not sit beside this script."""
    root = _normalise_path(root.strip())
    root = "" if root == "." else root
    prefix = f"{root}/" if root else ""
    files = sorted({p for p in (_normalise_path(p) for p in tree if isinstance(p, str) and p.strip())
                    if p.startswith(prefix)})
    if root and not files:
        raise ValueError(f"the tree lists no file under --root {root}")
    is_source = _sibling("skf-detect-language.py").is_source_file
    rel = [p[len(prefix):] for p in files]
    dirs = {"/".join(parts[:depth]) for parts in (r.split("/") for r in rel) for depth in range(1, len(parts))}
    detected = {"manifest_kind": None, "workspaces": [], "warnings": []}
    if not root:
        detected = detect({"tree": files, "manifests": manifests})
    base = _module_root(rel, dirs)
    # (files, source files) under each folder directly in the module root
    counts: dict[str, list[int]] = {}
    for path in rel:
        rest = path[len(base) + 1:] if base else path
        if (base and not path.startswith(base + "/")) or "/" not in rest or rest.startswith("."):
            continue
        tally = counts.setdefault(rest.split("/", 1)[0], [0, 0])
        tally[0] += 1
        tally[1] += int(is_source(path))
    module_root = prefix + base if base else root
    return {
        "root":                root,
        "truncated":           truncated,
        "file_count":          len(files),
        "source_file_count":   sum(1 for path in rel if is_source(path)),
        "dir_count":           len(dirs),
        "top_level_files":     sorted(r for r in rel if "/" not in r),
        "top_level_dirs":      sorted(d for d in dirs if "/" not in d),
        "manifest_kind":       detected["manifest_kind"],
        "workspaces":          detected["workspaces"],
        "module_root":         module_root,
        "module_candidates":   [
            {"path": f"{module_root}/{name}" if module_root else name,
             "file_count": tally[0], "source_file_count": tally[1]}
            for name, tally in sorted(counts.items())
        ],
        "registry_candidates": _sibling("skf-recommend-scope-type.py")._find_registry_files(files),
        "warnings":            detected["warnings"],
    }


# --------------------------------------------------------------------------
# Files: the tree listing, the manifests, the sibling scripts
# --------------------------------------------------------------------------


_SIBLINGS: dict[str, object] = {}


def _sibling(filename: str):
    """A helper of this folder, loaded once as a module: skf-detect-language.py
    reads a --tree-file listing, and skf-recommend-scope-type.py names the
    component registry files a snapshot lists. Raises ImportError when it
    does not sit beside this script."""
    module = _SIBLINGS.get(filename)
    if module is None:
        path = Path(__file__).resolve().parent / filename
        name = "skf_" + filename.removeprefix("skf-").removesuffix(".py").replace("-", "_")
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {filename} beside {Path(__file__).name}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except (OSError, SyntaxError) as exc:
            raise ImportError(f"cannot load {filename} beside {Path(__file__).name}: {exc}") from exc
        _SIBLINGS[filename] = module
    return module


def read_manifest_dir(folder: str, paths: list[str]) -> dict[str, str]:
    """{repo path: text} of each of `paths` read from `folder`, a folder laid
    out like the repository. A path outside the repository, or a file
    missing there, larger than MAX_MANIFEST_BYTES or not UTF-8, is left
    out: its content was not supplied."""
    out: dict[str, str] = {}
    for rel in dict.fromkeys(paths):
        if rel.startswith("/") or ".." in rel.split("/"):
            continue
        path = os.path.join(folder, *rel.split("/"))
        try:
            if os.path.getsize(path) > MAX_MANIFEST_BYTES:
                continue
            with open(path, "rb") as fh:
                out[rel] = fh.read().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
    return out


def _listed(tree: object) -> set[str]:
    return {_normalise_path(p) for p in tree if isinstance(p, str)} if isinstance(tree, list) else set()


def _fail(message: str, code: int) -> int:
    print(json.dumps({"error": message}), file=sys.stderr)
    return code


def _force_utf8(*streams) -> None:
    """Reconfigure the streams to UTF-8, keeping each one's error handler: a
    default Windows console reads stdin as cp1252, which cannot carry a
    UTF-8 payload or tree listing. For stdin this must run before the first
    read. Skips in-process test doubles without reconfigure()."""
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def _decode(raw: str) -> tuple[Optional[dict], Optional[str], int]:
    """(payload, error message, exit code) of a JSON payload's text."""
    if not raw.strip():
        return None, "empty input", 2
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"json decode error: {e}", 2
    if not isinstance(payload, dict):
        return None, "the payload must be a JSON object", 1
    return payload, None, 0


def main(argv: Optional[list[str]] = None) -> int:
    _force_utf8(sys.stdin, sys.stdout)
    parser = argparse.ArgumentParser(description="Detect monorepo / workspace layouts from a tree + manifests payload.")
    parser.add_argument("--json", help="Inline JSON payload (otherwise read from stdin).")
    parser.add_argument(
        "--tree-file",
        help="the repository's file list: JSON (a `tree` list, or a list) or one path per line; - reads stdin. "
             "With --tree-file <file>, stdin is not read: pass the manifests with --manifest-dir or --json",
    )
    parser.add_argument(
        "--manifest-dir",
        help="a folder laid out like the repository that holds the manifests (read as `manifests`)",
    )
    parser.add_argument(
        "--manifest-files",
        action="store_true",
        help="print the root manifests of the --tree-file listing whose content the detectors read, "
             "one path per line, and exit",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="print the tree snapshot (counts, top-level entries, workspaces, module candidates, registry files) "
             "instead",
    )
    parser.add_argument("--root", help="with --snapshot: the folder to describe (default: the repository)")
    args = parser.parse_args(argv)
    if args.manifest_files and (args.tree_file is None or args.json is not None or args.manifest_dir is not None
                                or args.snapshot or args.root is not None):
        return _fail("--manifest-files lists the root manifests of --tree-file and reads nothing else", 2)
    if args.root is not None and not args.snapshot:
        return _fail("--root names the folder --snapshot describes: pass --snapshot", 2)

    truncated = False
    if args.tree_file is not None:
        try:
            tree, truncated = _sibling("skf-detect-language.py").read_tree_file(args.tree_file)
        except (ImportError, ValueError) as e:  # ValueError: the sibling's TreeListingError
            return _fail(str(e), 2)
        if args.manifest_files:
            listed = _listed(tree)
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(newline="\n")  # a shell loop reads the lines: no CR on Windows
            sys.stdout.write("".join(f"{name}\n" for name in CONTENT_MANIFESTS if name in listed))
            return 0
        payload: dict = {}
        if args.json is not None:
            payload, message, code = _decode(args.json)
            if message:
                return _fail(message, code)
        if "tree" in payload:
            return _fail("pass the tree once: in the payload or with --tree-file, not both", 2)
        payload["tree"] = tree
        if args.manifest_dir is None:
            payload.setdefault("manifests", {})
    else:
        payload, message, code = _decode(args.json if args.json is not None else sys.stdin.read())
        if message:
            return _fail(message, code)
    if args.manifest_dir is not None:
        if "manifests" in payload:
            return _fail("pass the manifests once: in the payload or with --manifest-dir, not both", 2)
        listed = _listed(payload.get("tree"))
        payload["manifests"] = read_manifest_dir(args.manifest_dir, [n for n in CONTENT_MANIFESTS if n in listed])
        found = detect(payload)
        if found.get("workspaces"):
            # Each workspace's own manifest names it.
            payload["manifests"].update(
                read_manifest_dir(args.manifest_dir, [ws["manifest"] for ws in found["workspaces"]]))

    if args.snapshot:
        if not isinstance(payload.get("tree"), list):
            return _fail("missing or non-list 'tree' field", 1)
        if not isinstance(payload.get("manifests"), dict):
            return _fail("missing or non-dict 'manifests' field", 1)
        try:
            out = snapshot(payload["tree"], payload["manifests"], args.root or "", truncated)
        except (ImportError, ValueError) as e:  # a missing sibling, or a --root without files
            return _fail(str(e), 2)
        print(json.dumps(out, separators=(",", ":")))
        return 0

    result = detect(payload)
    if "_payload_error" in result:
        return _fail(result["_payload_error"], 1)
    if truncated:
        result["warnings"].append(
            "the --tree-file listing was cut short (truncated): a workspace whose manifest it does not list is missed")

    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
