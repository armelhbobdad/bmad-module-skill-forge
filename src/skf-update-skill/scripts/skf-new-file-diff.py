#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Deterministic NEW_FILE detection for skf-update-skill (detect-changes Category D).

`skf-hash-content compare` classifies files already tracked in the provenance
map (UNCHANGED / MODIFIED_FILE / DELETED_FILE) but by design cannot report a
file that is present in source yet absent from the provenance map: a NEW_FILE.
Deriving that set is a set-difference plus a filter with exactly one correct
answer per input: take every `source_file` in the scripts/assets inventory
(emitted by `skf-detect-scripts-assets detect`), subtract the paths already in
`file_entries[].source_file`, and set aside any user-authored `[MANUAL]` path,
any path the map's `entries[]` cite (code Category A and B track) and, with
--brief, any path the skill brief leaves out. Doing that subtraction in the
prompt drifts across runs; doing it here is byte-stable.

Usage:
  skf-detect-scripts-assets.py detect <source-root> \\
    | skf-new-file-diff.py <provenance-map-path> [--brief <brief-path>]

Reads the detect JSON on stdin (needs `scripts_inventory[]` and
`assets_inventory[]`, each row carrying `source_file`). Reads the provenance
map at the path argument (canonical `{file_entries: [...], entries: [...]}`
object, or a bare array of file entries). A map with no `file_entries`, or a
null one, tracks no file (a skill with no script, asset or promoted document,
or a map written before the field existed); a `file_entries` or `entries`
that is neither null nor an array is bad input.

--brief <brief-path> (the skill's skill-brief.yaml) keeps a detected path
only when the brief takes it, by update-skill Category A's in-scope test
(skf-classify-changed-files.py classify, with the glob rules of
skf-resolve-authoritative-files.py, both loaded from the shared scripts
folder): each `scope.include` and `scope.exclude` pattern normalized
(forward slashes, no leading `./`), and a path in scope when an include
matches it and no exclude does. With an empty `scope.include`, a path is in
scope when no exclude matches it and its extension is one a file the map's
`entries[]` cite has, or one the brief's `language` uses. The brief's
`scripts_intent` and `assets_intent` are honoured too: `none` drops every
detected path of that kind, and an absent or free-text intent detects.
An empty --brief (an unbound brief path) is a usage error, never an
unscoped run. Every path, the map's and the detector's, is compared
stripped, with forward slashes and no leading `./`.

Output JSON (stdout):
  {
    "new_files":       [ {"source_file": "...", "kind": "script|asset"}, ... ],
    "skipped_manual":  [ "...", ... ],   # under scripts/[MANUAL]/ or assets/[MANUAL]/
    "already_tracked": [ "...", ... ],   # present in file_entries
    "tracked_code":    [ "...", ... ],   # cited by entries[]: code, not a new file
    "out_of_scope":    [ "...", ... ],   # --brief: outside the brief's scope
    "intent_none":     [ "...", ... ],   # --brief: a kind whose intent is none
    "stats": {"inventory_total": N, "new": N,
              "skipped_manual": N, "already_tracked": N}
  }

Each detected path lands in exactly one list, tested in this order:
already_tracked, skipped_manual, tracked_code, out_of_scope, intent_none,
and new_files for the rest. All arrays are sorted by
source_file; new_files carries the kind of the inventory it came from
(scripts -> "script", assets -> "asset"). A path found in both inventories is
counted once, resolved as "script". The three set-aside lists (tracked_code,
out_of_scope, intent_none) are never counted in `stats`, whose
inventory_total still counts every detected path.

Exit codes:
  0  success (and --help)
  2  bad input (a usage error, unreadable/invalid stdin JSON, missing/invalid
     provenance map, a missing or unreadable brief, or a shared helper that
     cannot be loaded)
"""

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path, PurePosixPath

# scripts/[MANUAL]/... or assets/[MANUAL]/... anywhere in the (posix) path
_MANUAL_RE = re.compile(r"(?:^|/)(?:scripts|assets)/\[MANUAL\]/")

# The shared helpers the scope test reads: installed beside this skill's folder.
SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "shared" / "scripts"
RESOLVER = "skf-resolve-authoritative-files.py"
CLASSIFIER = "skf-classify-changed-files.py"

# kind -> the brief field that holds its intent
INTENT_FIELDS = {"script": "scripts_intent", "asset": "assets_intent"}

_SHARED: dict[str, object] = {}


def _fail(msg: str) -> "NoReturn":  # type: ignore[valid-type]
    print(json.dumps({"error": msg}), file=sys.stderr)
    sys.exit(2)


def _posix(p: str) -> str:
    """A path as skf-resolve-authoritative-files.py's normalize_rel_path
    writes it: stripped, forward slashes, no leading `./`."""
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _shared(filename: str):
    """A script of SHARED_SCRIPTS, loaded once; a failure to load it is bad input (exit 2)."""
    module = _SHARED.get(filename)
    if module is None:
        path = SHARED_SCRIPTS / filename
        try:
            spec = importlib.util.spec_from_file_location("skf_" + filename[:-3].replace("-", "_"), path)
            if spec is None or spec.loader is None or not path.is_file():
                raise ImportError(f"{filename} not found in {SHARED_SCRIPTS}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:  # whatever the script raises, the run reports it
            _fail(f"cannot load {filename} from {SHARED_SCRIPTS}: {exc}; re-install SKF")
        _SHARED[filename] = module
    return module


def _source_files(rows: list) -> set[str]:
    found: set[str] = set()
    for entry in rows:
        if isinstance(entry, dict):
            sf = entry.get("source_file")
            if isinstance(sf, str) and _posix(sf):
                found.add(_posix(sf))
    return found


def load_map_paths(provenance_path: Path) -> tuple[set[str], set[str]]:
    """(file_entries[].source_file, entries[].source_file) of the provenance map.

    A missing or null `file_entries` (or `entries`) is an empty list; one
    that is neither null nor an array is bad input. A bare array is the
    file entries themselves.
    """
    try:
        data = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _fail(f"failed to read provenance map {provenance_path}: {exc}")

    if isinstance(data, list):
        return _source_files(data), set()
    if not isinstance(data, dict):
        _fail(
            f"provenance map {provenance_path} must be an object or array; "
            f"got {type(data).__name__}"
        )
    rows = {}
    for key in ("file_entries", "entries"):
        value = data.get(key)
        if value is None:
            value = []  # a map that tracks no such row
        if not isinstance(value, list):
            _fail(f"`{key}` in {provenance_path} is not an array")
        rows[key] = value
    return _source_files(rows["file_entries"]), _source_files(rows["entries"])


def load_tracked_source_files(provenance_path: Path) -> set[str]:
    """Return the set of file_entries[].source_file already in the provenance map."""
    return load_map_paths(provenance_path)[0]


class Scope:
    """The brief's scope and intents, by update-skill Category A's in-scope test."""

    def __init__(self, includes: list[str], excludes: list[str], extensions: set[str],
                 intents: dict[str, str]):
        self.includes = includes
        self.excludes = excludes
        self.extensions = extensions
        self.intents = intents

    def takes(self, rel: str) -> bool:
        """True when the brief's scope takes `rel` (Category A's `_in_scope`)."""
        resolver = _shared(RESOLVER)
        rel = resolver.normalize_rel_path(rel)
        if self.includes:
            return resolver.scope_match(rel, self.includes, self.excludes)[0]
        if any(resolver.glob_match(rel, pattern) for pattern in self.excludes):
            return False
        return PurePosixPath(rel).suffix in self.extensions

    def wants(self, kind: str) -> bool:
        """False when the brief's intent for `kind` is `none`."""
        return self.intents.get(kind) != "none"


def _intent(value: object) -> str:
    """`none` for a `none` intent; `detect` for an absent or free-text one."""
    if isinstance(value, str) and value.strip().lower() == "none":
        return "none"
    return "detect"


def load_scope(brief_path: Path, cited: set[str]) -> Scope:
    """The brief's scope: its normalized include and exclude patterns (as
    skf-classify-changed-files.py classify normalizes them), the extensions
    an empty include falls back to (the cited code files' and the brief
    language's) and the script and asset intents."""
    if not brief_path.is_file():
        _fail(f"brief not found: {brief_path}")
    resolver = _shared(RESOLVER)
    try:
        brief = resolver.load_brief(brief_path)
    except ValueError as exc:
        _fail(str(exc))
    includes, excludes, _ = resolver.extract_scope(brief)
    norm = resolver.normalize_rel_path
    includes = [norm(p) for p in includes]
    excludes = [norm(p) for p in excludes]
    extensions: set[str] = set()
    if not includes:
        extensions = {PurePosixPath(p).suffix for p in cited if PurePosixPath(p).suffix}
        language = brief.get("language")
        if isinstance(language, str) and language.strip():
            extensions |= _shared(CLASSIFIER).language_extensions([language])[0]
    intents = {kind: _intent(brief.get(field)) for kind, field in INTENT_FIELDS.items()}
    return Scope(includes, excludes, extensions, intents)


def collect_inventory(detect: dict) -> list[tuple[str, str]]:
    """Return [(source_file, kind), ...] from the detect JSON, de-duplicated.

    Scripts win over assets when a path appears in both, so kind is stable.
    """
    seen: dict[str, str] = {}
    for key, kind in (("scripts_inventory", "script"), ("assets_inventory", "asset")):
        rows = detect.get(key)
        if rows is None:
            continue
        if not isinstance(rows, list):
            _fail(f"`{key}` in detect JSON is not an array")
        for row in rows:
            if not isinstance(row, dict):
                _fail(f"`{key}` entry is not an object: {row!r}")
            sf = row.get("source_file")
            if not isinstance(sf, str) or not sf:
                _fail(f"`{key}` entry missing string `source_file`: {row!r}")
            sf = _posix(sf)
            seen.setdefault(sf, kind)  # first inventory wins the kind
    return sorted(seen.items())


def diff(detect: dict, tracked: set[str], cited: set[str] | frozenset = frozenset(),
         scope: Scope | None = None) -> dict:
    new_files: list[dict] = []
    lists: dict[str, list[str]] = {name: [] for name in (
        "skipped_manual", "already_tracked", "tracked_code", "out_of_scope", "intent_none")}

    inventory = collect_inventory(detect)
    for sf, kind in inventory:
        if sf in tracked:
            lists["already_tracked"].append(sf)
        elif _MANUAL_RE.search(sf):
            lists["skipped_manual"].append(sf)
        elif sf in cited:
            lists["tracked_code"].append(sf)
        elif scope is not None and not scope.takes(sf):
            lists["out_of_scope"].append(sf)
        elif scope is not None and not scope.wants(kind):
            lists["intent_none"].append(sf)
        else:
            new_files.append({"source_file": sf, "kind": kind})

    return {
        "new_files": new_files,
        "skipped_manual": sorted(lists["skipped_manual"]),
        "already_tracked": sorted(lists["already_tracked"]),
        "tracked_code": sorted(lists["tracked_code"]),
        "out_of_scope": sorted(lists["out_of_scope"]),
        "intent_none": sorted(lists["intent_none"]),
        "stats": {
            "inventory_total": len(inventory),
            "new": len(new_files),
            "skipped_manual": len(lists["skipped_manual"]),
            "already_tracked": len(lists["already_tracked"]),
        },
    }


USAGE = "usage: skf-new-file-diff.py <provenance-map-path> [--brief <brief-path>]  (detect JSON on stdin)"


class _JsonErrorParser(argparse.ArgumentParser):
    """Report a usage error as the JSON error and exit 2 every other bad input gets."""

    def error(self, message: str) -> "NoReturn":  # type: ignore[valid-type]
        _fail(f"{USAGE}: {message}")


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonErrorParser(
        prog="skf-new-file-diff.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "provenance_map",
        metavar="provenance-map-path",
        help="the skill's provenance-map.json (the detect JSON is read on stdin)",
    )
    parser.add_argument(
        "--brief",
        metavar="brief-path",
        help="the skill brief: keep only the paths its scope takes and its intents want",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv[1:])
    if args.brief is not None and not args.brief.strip():
        parser.error("--brief is empty (an unbound brief path?): pass the brief, or leave --brief out")

    provenance_path = Path(args.provenance_map)
    if not provenance_path.exists():
        _fail(f"provenance map not found: {provenance_path}")

    raw = sys.stdin.read()
    if not raw.strip():
        _fail("no detect JSON on stdin")
    try:
        detect = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail(f"invalid detect JSON on stdin: {exc}")
    if not isinstance(detect, dict):
        _fail(f"detect JSON must be an object; got {type(detect).__name__}")

    tracked, cited = load_map_paths(provenance_path)
    scope = load_scope(Path(args.brief), cited) if args.brief is not None else None
    result = diff(detect, tracked, cited, scope)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
