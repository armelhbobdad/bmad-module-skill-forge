# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF Compare File Hashes: script/asset/doc drift detection for audit-skill.

This script replaces the per-file hash-compute-and-classify prose at
`src/skf-audit-skill/references/structural-diff.md` §4b (Script/Asset Drift).
It compares the `file_entries[]` block of a provenance map against the
current state of the source tree and emits three drift categories:

  - **added**:   with --brief, files present in the source tree but NOT
                 recorded in `file_entries[]` that the skill brief takes.
                 The walk is restricted to the standard script, asset
                 and doc folders (scripts/, bin/, tools/, cli/, assets/,
                 templates/, schemas/, configs/, examples/ at any depth,
                 and docs/authoritative/) and skips binary extensions,
                 generated paths and symbolic links. A module of a Python
                 package named like a script folder is code, not a
                 script: the detector's rule (is_package_module of
                 skf-detect-scripts-assets.py, loaded from this folder)
                 leaves it out unless it runs on its own (a shebang, a
                 top-level `__main__` block or the package's
                 `__main__.py`). Without --brief, or with a brief it cannot
                 read, no new file is looked for: `added` is empty and
                 `added_not_checked` says why.
  - **removed**: files in `file_entries[]` whose `source_file` is gone
                 from disk under `<source-root>`.
  - **changed**: files in `file_entries[]` present on disk but with a
                 different content hash than the stored hash.

--brief <skill-brief.yaml> keeps a walked file as added only when the
brief's scope takes it, by the one brief-scope test of
skf-classify-changed-files.py (load_scope, loaded from this folder only
when --brief is given), which update-skill's Category A and Category D
and create-skill's script and asset detector use too: with the glob rules
of skf-resolve-authoritative-files.py, and, for an empty `scope.include`,
the extensions of the map's `entries[]` files and of the brief's
`language`. A file the map's `entries[]` cite is code, never an added file
(update-skill's `tracked_code`). A file under a script folder is a script
and any other walked file an asset, except a docs/authoritative/ file, a
document: a script or an asset whose `scripts_intent` or `assets_intent`
is `none` is no added file, and no intent filters a document.

Distinct from `skf-hash-content.py compare`: that script classifies entries
that ARE in the provenance map (UNCHANGED / MODIFIED_FILE / DELETED_FILE).
audit-skill additionally needs the **inverse walk**: what new
script/asset/doc files have appeared in the source tree since the skill
was created? That's `added[]`. The sha256 helper is the one
skf-detect-scripts-assets.py has, kept here so hashing needs no other file.

Hash-prefix normalization (writer-vs-reader compatibility): stored hashes
in `file_entries[].content_hash` carry a `sha256:` prefix by SKF convention
(see `skf-create-skill/references/extraction-patterns-tracing.md` §Provenance).
The reader-side normalization here is unconditionally safe — strip any
lowercase-alphanumeric prefix terminated by `:` before comparing, and
re-emit the stored value as-given in the diff record so reviewers can see
the original form. A bare-hex hash from a future writer would pass through
unchanged.

Subcommand:
  compare <provenance-map.json> <source-root> [--brief <skill-brief.yaml>]
      Emit JSON:
        {
          "added": ["<rel-path, forward-slash>", ...],
          "added_not_checked": null | "<reason>",
          "removed": ["<rel-path, forward-slash>", ...],
          "changed": [
            {"path": "<rel-path>", "stored_hash": "sha256:...",
             "current_hash": "sha256:..."}, ...
          ],
          "stats": {"added": N, "removed": N, "changed": N, "unchanged": N}
        }

      All paths are forward-slash relative to `<source-root>`. Stable sort
      on the lists for deterministic output (lexicographic on path).
      `added_not_checked` is null when the walk ran, else the reason no
      new file was looked for, on one line: `no skill brief` without
      --brief (or with an empty one), the error the brief gave
      (`brief not found: <path>`, or a brief that is not valid YAML or no
      mapping), or `cannot load <helper> beside skf-compare-file-hashes.py:
      ...; re-install SKF` when a helper of this folder the walk needs
      cannot be loaded or is out of date. `stats.added` counts `added`.

CLI examples:
  uv run skf-compare-file-hashes.py compare prov-map.json /path/to/src \\
      --brief skill-brief.yaml

Exit codes:
  0  comparison succeeded (including empty/well-formed input that yields
     all-empty drift lists, and a brief or a helper of this folder it
     cannot read or load: see `added_not_checked`)
  1  user error (missing files, malformed JSON, unreadable paths)
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Iterable


# --------------------------------------------------------------------------
# Constants: mirror skf-detect-scripts-assets.py so the inverse walk
# explores the same set of trees the writer side would have considered.
# --------------------------------------------------------------------------


SCRIPT_DIRS = {"scripts", "bin", "tools", "cli"}
ASSET_DIRS = {"assets", "templates", "schemas", "configs", "examples"}
DOC_DIR_PREFIXES = ("docs/authoritative/",)  # synthetic namespace from create-skill §6

# Path-segment names that mark generated/vendored output trees — pruned
# from the walk so the inverse never reports build-tree artifacts as added.
EXCLUDED_DIR_NAMES = {
    "node_modules", "__pycache__", "dist", "build", ".webpack",
    "target", ".next", ".nuxt", "out", "coverage", ".git",
    ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".gradle", ".idea", ".vscode",
}

BINARY_EXTS = {
    ".so", ".dll", ".jar", ".wasm", ".exe", ".dylib", ".a", ".o",
    ".pyc", ".class", ".png", ".jpg", ".jpeg", ".gif", ".ico",
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
}


_HASH_PREFIX_RE = re.compile(r"^[a-z0-9]+:")

DETECTOR = "skf-detect-scripts-assets.py"    # is_package_module: the package rule
CLASSIFIER = "skf-classify-changed-files.py"  # load_scope: the brief's scope (--brief)
NO_BRIEF = "no skill brief"

_SIBLINGS: dict[str, object] = {}


class HelperError(Exception):
    """A helper beside this script that cannot be loaded, lacks what this
    script calls or fails in it: no new file can be looked for."""


def _helper_error(filename: str, exc: BaseException) -> HelperError:
    return HelperError(f"cannot load {filename} beside {Path(__file__).name}: {exc}; re-install SKF")


def _sibling(filename: str):
    """A helper installed beside this script, loaded once as a module.
    Raises HelperError when it cannot be loaded."""
    module = _SIBLINGS.get(filename)
    if module is None:
        path = Path(__file__).resolve().parent / filename
        name = "skf_" + filename.removeprefix("skf-").removesuffix(".py").replace("-", "_")
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None or not path.is_file():
                raise ImportError(f"{filename} not found")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:  # whatever the helper raises, the run reports it
            raise _helper_error(filename, exc) from exc
        _SIBLINGS[filename] = module
    return module


def _is_package_module(entry: Path, source_root: Path) -> bool:
    """The detector's is_package_module. Raises HelperError when the detector
    cannot be loaded, lacks it or fails in it."""
    detector = _sibling(DETECTOR)
    try:
        return bool(detector.is_package_module(entry, source_root))
    except Exception as exc:
        raise _helper_error(DETECTOR, exc) from exc


def _posix(p: str) -> str:
    """A path as skf-resolve-authoritative-files.py's normalize_rel_path
    writes it: stripped, forward slashes, no leading `./`."""
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _one_line(message: str) -> str:
    """Each line break of `message` and the space around it as one space
    (a YAML error spans several lines)."""
    return re.sub(r"\s*[\r\n]\s*", " ", message.strip("\r\n"))


# --------------------------------------------------------------------------
# Hash + normalization primitives
# --------------------------------------------------------------------------


def sha256_of_file(path: Path) -> str:
    """SHA-256 of file content, with sha256: prefix. Matches the convention
    used by skf-hash-content.py / skf-detect-scripts-assets.py."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def normalize_hash(value: str | None) -> str | None:
    """Strip a leading algorithm-name prefix (`sha256:`, `sha1:`, etc.)
    from a stored hash so bare-hex and prefixed forms compare equal.

    Returns None if input is None or non-string. Idempotent on bare hex.
    """
    if not isinstance(value, str):
        return None
    return _HASH_PREFIX_RE.sub("", value, count=1)


# --------------------------------------------------------------------------
# Provenance load — same shape-tolerance as skf-hash-content.load_file_entries
# --------------------------------------------------------------------------


def _read_map(provenance_path: Path) -> object:
    """The provenance map's JSON. Raises ValueError when it cannot be read."""
    try:
        text = provenance_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"failed to read provenance file {provenance_path}: {exc}"
        ) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"malformed JSON in provenance file {provenance_path}: {exc}"
        ) from exc


def load_file_entries(provenance_path: Path) -> list[dict]:
    """Extract `file_entries[]` from a provenance map. Accepts:
      - top-level object with a `file_entries` key (canonical)
      - top-level array (already extracted)
      - top-level object with NO `file_entries` field → empty list
        (a single-skill with no scripts/assets/docs may omit the field
        entirely per skill-sections.md §file_entries)

    Raises ValueError on read failure or structural defects.
    """
    return _file_entries(_read_map(provenance_path), provenance_path)


def _file_entries(data: object, provenance_path: Path) -> list[dict]:
    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict):
        entries = data.get("file_entries")
        if entries is None:
            return []  # provenance with no tracked file_entries is valid
        if not isinstance(entries, list):
            raise ValueError(
                f"`file_entries` in {provenance_path} is not an array"
            )
        return list(entries)
    raise ValueError(
        f"provenance file {provenance_path} must be an object or array; "
        f"got {type(data).__name__}"
    )


def _cited(data: object) -> set[str]:
    """The map's `entries[].source_file`, the code files it cites (none for
    a bare array, or an `entries` that is not a list)."""
    rows = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return set()
    return {
        _posix(row["source_file"])
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("source_file"), str) and _posix(row["source_file"])
    }


# --------------------------------------------------------------------------
# Walk: the inverse direction (source tree to candidate set)
# --------------------------------------------------------------------------


def _segment_in_excluded(rel_parts: tuple[str, ...]) -> bool:
    return any(seg in EXCLUDED_DIR_NAMES for seg in rel_parts)


def _segment_in_tracked_dir(rel_parts: tuple[str, ...]) -> bool:
    """True if any segment of the relative path is a tracked script/asset
    directory."""
    for seg in rel_parts:
        if seg in SCRIPT_DIRS or seg in ASSET_DIRS:
            return True
    return False


def _matches_doc_prefix(rel_posix: str) -> bool:
    return any(rel_posix.startswith(p) for p in DOC_DIR_PREFIXES)


def _kind(entry: Path, source_root: Path, rel_parts: tuple[str, ...], rel_posix: str) -> str | None:
    """`doc`, `script` or `asset` for a walked file, or None for a file the
    walk leaves out. A docs/authoritative/ file is a document; a file under
    a script folder a script, unless it is a module of a Python package
    named like one (the detector's is_package_module, loaded only for a
    file under a script folder); any other file under an asset folder an
    asset."""
    if _matches_doc_prefix(rel_posix):
        return "doc"
    if any(seg in SCRIPT_DIRS for seg in rel_parts) and not _is_package_module(entry, source_root):
        return "script"
    if any(seg in ASSET_DIRS for seg in rel_parts):
        return "asset"
    return None


def _walk(source_root: Path) -> Iterable[tuple[str, str]]:
    """(POSIX relative path, kind) of each file under source_root that could
    be tracked as a script, asset or doc file_entries row (see _kind)."""
    stack: list[Path] = [source_root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (PermissionError, FileNotFoundError):
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in EXCLUDED_DIR_NAMES:
                    continue
                stack.append(entry)
                continue
            if not entry.is_file():
                continue
            if entry.suffix.lower() in BINARY_EXTS:
                continue
            try:
                rel = entry.relative_to(source_root)
            except ValueError:
                continue
            rel_parts = rel.parts[:-1]
            rel_posix = rel.as_posix()
            if not (_segment_in_tracked_dir(rel_parts) or _matches_doc_prefix(rel_posix)):
                continue
            kind = _kind(entry, source_root, rel_parts, rel_posix)
            if kind is not None:
                yield rel_posix, kind


def candidate_source_files(source_root: Path) -> Iterable[str]:
    """Yield POSIX relative paths under source_root that could be tracked
    as script / asset / doc file_entries.

    Selection rules:
      - File is under a SCRIPT_DIRS or ASSET_DIRS directory at any depth, OR
      - File path matches a DOC_DIR_PREFIXES synthetic namespace.
      - A module of a Python package named like a script folder is code,
        not a script (skf-detect-scripts-assets.py is_package_module): it
        is left out unless an asset folder holds it too.
      - Binary extensions are excluded.
      - Generated/vendored directories are pruned from the walk.

    This is deliberately narrower than "every file": audit-skill §4b only
    tracks files matching script/asset patterns. Treating every random
    source file as a candidate `added` row would drown real drift in noise.
    Raises HelperError when the detector cannot be loaded.
    """
    for rel, _kind_ in _walk(source_root):
        yield rel


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------


def compare(source_root: Path, provenance_path: Path, brief_path: Path | None = None) -> dict:
    """Compute added / removed / changed / unchanged for tracked file_entries.

    Stored hashes are normalized before comparison; the diff record carries
    the original stored value (writer-form) plus the freshly computed
    current value (always prefixed sha256:) so reviewers see both. Added
    files are looked for only with a brief it can read (`brief_path`):
    otherwise `added` is empty and `added_not_checked` says why, as it
    does when a helper the walk needs cannot be loaded. Raises ValueError
    for a map it cannot read.
    """
    data = _read_map(provenance_path)
    entries = _file_entries(data, provenance_path)
    # Build the {posix_path -> stored_hash} index from the provenance.
    stored: dict[str, str | None] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        sf = entry.get("source_file")
        if not isinstance(sf, str) or not sf:
            continue
        stored[sf.replace("\\", "/")] = entry.get("content_hash") if isinstance(
            entry.get("content_hash"), str
        ) else None

    removed: list[str] = []
    changed: list[dict] = []
    unchanged_count = 0

    for path, stored_hash in sorted(stored.items()):
        full = source_root / path
        if not full.is_file():
            removed.append(path)
            continue
        current = sha256_of_file(full)
        if normalize_hash(stored_hash) == normalize_hash(current):
            unchanged_count += 1
        else:
            changed.append({
                "path": path,
                "stored_hash": stored_hash,
                "current_hash": current,
            })

    added, not_checked = _added(source_root, data, stored, brief_path)

    return {
        "added": added,
        "added_not_checked": not_checked,
        "removed": sorted(removed),
        "changed": sorted(changed, key=lambda r: r["path"]),
        "stats": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": unchanged_count,
        },
    }


def _added(source_root: Path, data: object, stored: dict, brief_path: Path | None) -> tuple[list[str], str | None]:
    """(added, added_not_checked): the walked files the map does not track
    and the brief takes, or ([], the reason) without a brief it can read or
    a helper the walk needs. removed and changed need neither."""
    if brief_path is None:
        return [], NO_BRIEF
    cited = _cited(data)
    try:
        try:
            scope = _sibling(CLASSIFIER).load_scope(brief_path, cited)
        except ValueError as exc:  # a brief it cannot find or read
            return [], _one_line(str(exc))
        except HelperError:
            raise
        except Exception as exc:  # an out-of-date classifier, or a resolver beside it that cannot load
            raise _helper_error(CLASSIFIER, exc) from exc
        known = {_posix(path) for path in stored}
        added = []
        for rel, kind in _walk(source_root):
            if rel in known or rel in cited:  # tracked, or code the map's entries[] cite
                continue
            if not _scope_call(scope.takes, rel):
                continue
            if kind != "doc" and not _scope_call(scope.wants, kind):
                continue
            added.append(rel)
    except HelperError as exc:
        return [], _one_line(str(exc))
    return sorted(added), None


def _scope_call(method, value) -> bool:
    """A Scope method's answer. Raises HelperError when it fails (the
    resolver it calls cannot be loaded or is out of date)."""
    try:
        return bool(method(value))
    except Exception as exc:
        raise _helper_error(CLASSIFIER, exc) from exc


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_compare(args: argparse.Namespace) -> int:
    provenance = Path(args.provenance_map)
    source_root = Path(args.source_root)
    if not provenance.is_file():
        print(f"error: provenance map not found: {provenance}", file=sys.stderr)
        return 1
    if not source_root.is_dir():
        print(f"error: source root not a directory: {source_root}", file=sys.stderr)
        return 1
    brief = Path(args.brief) if args.brief is not None and args.brief.strip() else None
    try:
        result = compare(source_root, provenance, brief)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-compare-file-hashes",
        description=(
            "Compare provenance file_entries[] against the current source "
            "tree to detect script/asset/doc drift (added/removed/changed)."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_cmp = sub.add_parser(
        "compare",
        help="classify tracked file_entries[] + walk inverse to detect added files",
    )
    p_cmp.add_argument("provenance_map", help="path to provenance-map.json")
    p_cmp.add_argument("source_root", help="path to the source tree root")
    p_cmp.add_argument(
        "--brief",
        default=None,
        metavar="BRIEF",
        help="the skill brief (skill-brief.yaml): look for added files only in its scope "
             "(none, or one it cannot read: no added file is looked for)",
    )
    p_cmp.set_defaults(func=_cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
