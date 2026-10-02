# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""SKF Recommend Scope Type: the scope-type ladder, applied to facts and to
the intent signals the caller classified.

Single source of truth for the scope-type recommendation that
skf-brief-skill step 3 §2c presents and a headless run applies. Both
paths call this script with the same inputs, so they cannot drift.

The script reads no free text. What a user's intent asks for is a
judgment: "the whole library, not just the parser" names no module, and
"Kickstarter-style" asks for no starter app although it contains the word.
So the caller reads the intent and passes three typed signals, and the
script keeps only the rules that rest on facts (the file tree, a registry
file's contents, the module and export counts, the source type) and the
order of the ladder.

The ladder (first match wins):

  0. docs-only          source_type is docs-only: no source surface to scope
  1. component-library  a registry.ts / components.ts (or .tsx) at any depth
                        of the tree whose contents (entry_files, or
                        --entry-dir) show 10+ entries or a Component[]
                        annotation. In headless mode, a registry file whose
                        contents were not given counts by its presence.
  2. reference-app      signal wants_wiring_pattern
  3. specific-modules   signal named_module_subset is not empty, else
                        module_count >= 6
  4. public-api         signal wants_narrow_api and 0 < export_count <= 8
  5. full-library       no rule matched

CLI:
  uv run skf-recommend-scope-type.py --tree-file <file> [--entry-dir <dir>] < payload.json
  uv run skf-recommend-scope-type.py --tree-file <file> --json '{...}'
  <listing> | uv run skf-recommend-scope-type.py --tree-file - --json '{...}'
  uv run skf-recommend-scope-type.py --tree-file <file> --registry-files

--tree-file reads the repository's file list from a file (`-` reads it from
stdin, and the payload then comes with --json):
  - JSON: an object whose `tree` lists the paths, such as the output of
    skf-github-probe.py tree (a listing whose `status` is not "ok" is
    refused, with its `message`) or a GitHub git/trees response (only its
    `blob` entries count); or a JSON list of paths.
  - Anything else: one path per line, as `git -c core.quotePath=false
    ls-files` prints them (a leading `./`, as `find .` prints it, is
    dropped).
The payload may carry the list as `tree` instead; passing both is an error.

--registry-files prints the registry files the --tree-file listing holds,
one repo path per line with LF endings on every platform (nothing when there
are none), and exits without reading a payload: a shell loop fetches exactly
those files.

--entry-dir reads each registry file the tree lists from <dir>/<repo path>,
as the payload's `entry_files`: a local checkout, or the folder the caller
fetched the --registry-files paths into. A registry file missing there is
one whose contents were not given. Passing `entry_files` too is an error.

Input (JSON object on stdin or via --json):
  signals       object, required unless source_type is docs-only. Exactly
                these keys, classified by the caller from the user's intent
                and scope hints:
                  wants_wiring_pattern  true | false: the user wants how an
                                        app, starter or example wires its
                                        parts together, not a library's API
                  named_module_subset   the module names the user limits the
                                        skill to ([] when none)
                  wants_narrow_api      true | false: the user wants only the
                                        public API, SDK or client surface
  module_count  integer >= 0 (top-level modules from step 2), default 0
  export_count  integer >= 0 (named exports from step 2), default 0
  tree          list of repo-relative file paths, default [] (or --tree-file)
  entry_files   optional [{path, content}]: the registry files' contents
                (or --entry-dir)
  source_type   "source" | "docs-only" | null, default null
  mode          "interactive" | "headless", default "headless"
A payload that carries free text (`intent`, `scope_hint`) or any other key
is refused.

Output (JSON on stdout):
  scope_type        full-library | specific-modules | public-api
                    | component-library | reference-app | docs-only
  matched_heuristic "docs-only-shortcircuit" | "component-registry"
                    | "reference-app-intent" | "specific-modules-naming"
                    | "specific-modules-count" | "narrow-public-api"
                    | "default-full-library"
  signals           what fired (a path, a count, the signal values)
  rationale         one sentence naming what fired

Exit codes:
  0  recommendation produced (or, with --registry-files, the list printed)
  2  bad input: invalid JSON, an unknown or mistyped key, no signals object,
     the tree or the registry contents passed twice, or a tree listing that
     cannot be read, is empty or reports a failure
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

SIGNAL_KEYS = ("wants_wiring_pattern", "named_module_subset", "wants_narrow_api")
PAYLOAD_KEYS = frozenset({"signals", "module_count", "export_count", "tree", "entry_files", "source_type", "mode"})
# Free-text keys (the old payload carried `intent`), refused by name: the
# script reads no free text.
FREE_TEXT_KEYS = ("intent", "scope_hint")
# A --tree-file listing is JSON when it opens like a JSON object or list of
# paths. A bare leading bracket is not enough: a line listing can start with
# a path such as `[slug]/page.tsx`.
JSON_LISTING_RE = re.compile(r'\{\s*["}]|\[\s*["{\]]')

VALID_MODES = {"interactive", "headless"}
VALID_SOURCE_TYPES = {None, "source", "docs-only"}


def _die(message: str, code: int = 2) -> None:
    sys.stderr.write(f"skf-recommend-scope-type: {message}\n")
    sys.exit(code)


def _find_registry_files(tree: list[str]) -> list[str]:
    """Return repo-relative paths matching registry.ts / components.ts (any depth)."""
    hits: list[str] = []
    for path in tree:
        if not isinstance(path, str):
            continue
        parts = path.split("/")
        # Never a path outside the repository: --registry-files feeds a shell
        # loop that writes each file under a folder.
        if path.startswith("/") or ".." in parts:
            continue
        if parts[-1] in {"registry.ts", "components.ts", "registry.tsx", "components.tsx"}:
            hits.append(path)
    return hits


def _registry_entry_count(content: str) -> int:
    """Approximate the number of entries in a registry array literal.

    Counts top-level `{ ... }` objects within the first array-like body
    we encounter. Approximate by design — used only as a >=10 threshold.
    """
    # Strip line comments to reduce noise; do not bother with block comments.
    cleaned = re.sub(r"//.*", "", content)
    # Find array literals — match `[` followed by whitespace then `{`.
    array_match = re.search(r"\[\s*\{", cleaned)
    if not array_match:
        return 0
    body_start = array_match.start()
    # Walk forward, count balanced top-level `{` matches up to the closing `]`.
    depth = 0
    in_string: str | None = None
    count = 0
    for ch in cleaned[body_start:]:
        if in_string:
            if ch == in_string:
                in_string = None
            continue
        if ch in ("'", '"', "`"):
            in_string = ch
            continue
        if ch == "{":
            if depth == 0:
                count += 1
            depth += 1
        elif ch == "}":
            depth = max(depth - 1, 0)
        elif ch == "]" and depth == 0:
            break
    return count


def _has_component_array_annotation(content: str) -> bool:
    """Detect a `Component[]` type annotation, allowing trivial whitespace and generics."""
    return bool(re.search(r"\bComponent(?:\s*<[^>]*>)?\s*\[\s*\]", content))


def _component_registry_match(
    tree: list[str],
    entry_files: list[dict] | None,
    mode: str,
) -> dict | None:
    """Apply rule 1 — component-library.

    Returns a signals dict on match, or None.
    """
    registry_paths = _find_registry_files(tree)
    if not registry_paths:
        return None

    # Index entry-file contents by path for O(1) lookup
    contents: dict[str, str] = {}
    if entry_files:
        for ef in entry_files:
            if not isinstance(ef, dict):
                continue
            path = ef.get("path")
            content = ef.get("content")
            if isinstance(path, str) and isinstance(content, str):
                contents[path] = content

    # A registry file with contents is judged by them; one without contents
    # counts by its presence in headless mode only.
    not_given: list[str] = []
    for path in registry_paths:
        if path not in contents:
            not_given.append(path)
            continue
        entry_count = _registry_entry_count(contents[path])
        has_annotation = _has_component_array_annotation(contents[path])
        if entry_count >= 10 or has_annotation:
            return {
                "registry_path": path,
                "entry_count": entry_count if entry_count >= 10 else None,
                "component_array_annotation": has_annotation,
                "contents_inspected": True,
            }
        # Neither threshold met: the contents disqualify this file

    if mode == "headless" and not_given:
        return {
            "registry_path": not_given[0],
            "entry_count": None,
            "component_array_annotation": False,
            "contents_inspected": False,
        }
    # Interactive without contents: the rule does not match
    return None


def _read_signals(payload: dict) -> dict:
    """The caller's classified intent signals, checked for shape."""
    signals = payload.get("signals")
    wanted = ", ".join(SIGNAL_KEYS)
    if not isinstance(signals, dict):
        _die(f"signals must be an object with {wanted}, classified from the user's intent; got {signals!r}")
    unknown = sorted(set(signals) - set(SIGNAL_KEYS))
    missing = [key for key in SIGNAL_KEYS if key not in signals]
    if unknown or missing:
        _die(f"signals must have exactly {wanted}; unknown {unknown}, missing {missing}")
    for key in ("wants_wiring_pattern", "wants_narrow_api"):
        if not isinstance(signals[key], bool):
            _die(f"signals.{key} must be true or false; got {signals[key]!r}")
    names = signals["named_module_subset"]
    if not isinstance(names, list) or not all(isinstance(n, str) and n.strip() for n in names):
        _die(f"signals.named_module_subset must be a list of module names ([] when the intent names none); got {names!r}")
    return {
        "wants_wiring_pattern": signals["wants_wiring_pattern"],
        "named_module_subset": [n.strip() for n in names],
        "wants_narrow_api": signals["wants_narrow_api"],
    }


def _count(payload: dict, key: str) -> int:
    value = payload.get(key)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _die(f"{key} must be a whole number >= 0; got {value!r}")
    return value


def _specific_modules_match(named: list[str], module_count: int) -> tuple[str, dict] | None:
    if named:
        return ("specific-modules-naming", {"named_module_subset": named})
    if module_count >= 6:
        return ("specific-modules-count", {"module_count": module_count})
    return None


def recommend(payload: dict) -> dict:
    """Apply the ladder. Always returns a recommendation."""
    for key in FREE_TEXT_KEYS:
        if key in payload:
            _die(f"{key} is free text, which this script no longer reads: classify it into signals "
                 f"({', '.join(SIGNAL_KEYS)}) and pass those")
    unknown = sorted(set(payload) - PAYLOAD_KEYS)
    if unknown:
        _die(f"unknown payload keys {unknown}; expected {sorted(PAYLOAD_KEYS)}")

    tree = payload.get("tree")
    if tree is None:
        tree = []
    if not isinstance(tree, list):
        _die(f"tree must be a list of file paths; got {type(tree).__name__}")
    entry_files = payload.get("entry_files")
    source_type = payload.get("source_type")
    mode = payload.get("mode") or "headless"

    if source_type not in VALID_SOURCE_TYPES:
        _die(f"source_type must be one of {sorted(t for t in VALID_SOURCE_TYPES if t)} or null; got {source_type!r}")
    if mode not in VALID_MODES:
        _die(f"mode must be one of {sorted(VALID_MODES)}; got {mode!r}")
    module_count = _count(payload, "module_count")
    export_count = _count(payload, "export_count")

    # Short-circuit: docs-only has no source surface to scope, and needs no signals
    if source_type == "docs-only":
        if "signals" in payload:
            _read_signals(payload)
        return {
            "scope_type": "docs-only",
            "matched_heuristic": "docs-only-shortcircuit",
            "signals": {"source_type": "docs-only"},
            "rationale": "Docs Only because source_type is docs-only: there is no source surface to scope, so the brief uses the docs-only template.",
        }

    signals = _read_signals(payload)

    # Rule 1: component-library
    cr = _component_registry_match(tree, entry_files, mode)
    if cr:
        rationale_bits = [f"a component registry was detected at {cr['registry_path']}"]
        if cr.get("entry_count"):
            rationale_bits.append(f"with {cr['entry_count']} entries")
        if cr.get("component_array_annotation"):
            rationale_bits.append("and a Component[] type annotation")
        if not cr.get("contents_inspected"):
            rationale_bits.append("(presence-only match: file contents not inspected in headless mode)")
        return {
            "scope_type": "component-library",
            "matched_heuristic": "component-registry",
            "signals": cr,
            "rationale": "Component Library because " + " ".join(rationale_bits) + ".",
        }

    # Rule 2: reference-app
    if signals["wants_wiring_pattern"]:
        return {
            "scope_type": "reference-app",
            "matched_heuristic": "reference-app-intent",
            "signals": {"wants_wiring_pattern": True},
            "rationale": "Reference App because the intent asks how an app, starter or example wires its parts together, a wiring-pattern skill rather than a library API.",
        }

    # Rule 3: specific-modules
    sm = _specific_modules_match(signals["named_module_subset"], module_count)
    if sm:
        heuristic, fired = sm
        if heuristic == "specific-modules-naming":
            rationale = f"Specific Modules because the intent limits the skill to {', '.join(fired['named_module_subset'])}."
        else:
            rationale = f"Specific Modules because the analysis surfaced {fired['module_count']} top-level modules, likely too many for a single cohesive scope."
        return {
            "scope_type": "specific-modules",
            "matched_heuristic": heuristic,
            "signals": fired,
            "rationale": rationale,
        }

    # Rule 4: narrow public API
    if signals["wants_narrow_api"] and 0 < export_count <= 8:
        return {
            "scope_type": "public-api",
            "matched_heuristic": "narrow-public-api",
            "signals": {"wants_narrow_api": True, "export_count": export_count},
            "rationale": f"Public API Only because the intent asks for the public API only and the manifest exposes {export_count} named exports, a clear narrow public surface.",
        }

    # Rule 5: fallback
    return {
        "scope_type": "full-library",
        "matched_heuristic": "default-full-library",
        "signals": {
            "module_count": module_count,
            "export_count": export_count,
        },
        "rationale": "Full Library because no signal matched a narrower scope, so the default is to cover everything.",
    }


def _parse_tree_listing(text: str, source: str) -> list[str]:
    """The file paths a --tree-file listing names: JSON, or one path per line."""
    stripped = text.strip()
    if not stripped:
        _die(f"the tree listing {source} is empty; the command that wrote it may have failed")
    if not JSON_LISTING_RE.match(stripped):
        paths = []
        for line in stripped.splitlines():
            path = line.strip().removeprefix("./")
            if path:
                paths.append(path)
        return paths
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        _die(f"the tree listing {source} is not valid JSON: {e}")
    entries = data
    if isinstance(data, dict):
        status = data.get("status")
        if status is not None and status != "ok":
            _die(f"the tree listing {source} reports a failure ({status}): {data.get('message') or 'no message'}")
        entries = data.get("tree")
    if not isinstance(entries, list):
        _die(f"the tree listing {source} holds no list of paths (a `tree` list, or a JSON list)")
    paths = []
    for entry in entries:
        if isinstance(entry, str):
            paths.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry.get("type", "blob") == "blob":
            paths.append(entry["path"])
    return paths


def _read_tree_file(value: str) -> list[str]:
    if value == "-":
        return _parse_tree_listing(sys.stdin.read(), "on stdin")
    try:
        with open(value, encoding="utf-8-sig") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as e:
        _die(f"cannot read --tree-file {value}: {getattr(e, 'strerror', None) or e}")
    return _parse_tree_listing(text, f"in {value}")


def _read_entry_dir(folder: str, tree: object) -> list[dict]:
    """The registry files the tree lists, read from `folder` laid out like the repository."""
    files = []
    for path in _find_registry_files(tree if isinstance(tree, list) else []):
        try:
            with open(os.path.join(folder, *path.split("/")), encoding="utf-8", errors="replace") as fh:
                files.append({"path": path, "content": fh.read()})
        except OSError:
            continue  # not fetched: its contents were not given
    return files


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recommend a scope type: the documented ladder over facts and classified intent signals.",
    )
    parser.add_argument(
        "--json",
        help="JSON payload (alternative to stdin)",
    )
    parser.add_argument(
        "--tree-file",
        help="the repository's file list: JSON (a `tree` list, or a list) or one path per line; - reads stdin",
    )
    parser.add_argument(
        "--entry-dir",
        help="a folder laid out like the repository that holds the registry files the tree lists (read as entry_files)",
    )
    parser.add_argument(
        "--registry-files",
        action="store_true",
        help="print the registry files the --tree-file listing holds, one path per line, and exit",
    )
    args = parser.parse_args(argv)
    if args.registry_files:
        if args.tree_file is None:
            _die("--registry-files lists the registry files of --tree-file, so pass it")
        if args.json is not None or args.entry_dir is not None:
            _die("--registry-files reads only --tree-file")
    elif args.tree_file == "-" and args.json is None:
        _die("--tree-file - reads the tree from stdin, so pass the payload with --json")
    return args


def _read_payload(args: argparse.Namespace) -> dict:
    if args.json is not None:
        raw = args.json
    else:
        raw = sys.stdin.read()
    if not raw or not raw.strip():
        _die("empty input (expected JSON payload on stdin or via --json)")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(f"invalid JSON input: {e}")
    if not isinstance(payload, dict):
        _die("payload must be a JSON object")
    if args.tree_file is not None:
        if "tree" in payload:
            _die("pass the tree once: in the payload or with --tree-file, not both")
        payload["tree"] = _read_tree_file(args.tree_file)
    if args.entry_dir is not None:
        if "entry_files" in payload:
            _die("pass the registry contents once: as entry_files in the payload or with --entry-dir, not both")
        payload["entry_files"] = _read_entry_dir(args.entry_dir, payload.get("tree"))
    return payload


def _force_utf8(*streams) -> None:
    """Reconfigure JSON-carrying streams to UTF-8 (issue #465).

    A default Windows console decodes stdio as cp1252, which cannot carry
    non-ASCII JSON (ensure_ascii=False output, raw UTF-8 input). Preserves
    each stream's existing error handler — reconfigure(encoding=...) alone
    would reset it to 'strict', downgrading e.g. an already-UTF-8 stderr on
    Linux. For stdin this must run before the first read. Skips in-process
    test doubles without reconfigure().
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def main(argv: list[str]) -> int:
    _force_utf8(sys.stdin, sys.stdout)
    args = _parse_args(argv)
    if args.registry_files:
        paths = _find_registry_files(_read_tree_file(args.tree_file))
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(newline="\n")  # a shell loop reads the lines: no CR on Windows
        sys.stdout.write("".join(f"{path}\n" for path in paths))
        return 0
    payload = _read_payload(args)
    result = recommend(payload)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
