# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Compare File Hashes — script/asset/doc drift detection for audit-skill.

This script replaces the per-file hash-compute-and-classify prose at
`src/skf-audit-skill/references/structural-diff.md` §4b (Script/Asset Drift).
It compares the `file_entries[]` block of a provenance map against the
current state of the source tree and emits three drift categories:

  - **added**:   files present in the source tree but NOT recorded in
                 `file_entries[]`. Walk is restricted to standard script/
                 asset/doc directories (scripts/, bin/, tools/, cli/,
                 assets/, templates/, schemas/, configs/, examples/) and
                 excludes binary extensions and generated paths — same
                 path discipline as `skf-detect-scripts-assets.py`.
  - **removed**: files in `file_entries[]` whose `source_file` is gone
                 from disk under `<source-root>`.
  - **changed**: files in `file_entries[]` present on disk but with a
                 different content hash than the stored hash.

Distinct from `skf-hash-content.py compare`: that script classifies entries
that ARE in the provenance map (UNCHANGED / MODIFIED_FILE / DELETED_FILE).
audit-skill additionally needs the **inverse walk** — what new
script/asset/doc files have appeared in the source tree since the skill
was created? That's `added[]`. We delegate the path-resolution and
hash-comparison logic for entries IN the map by duplicating the small
sha256 helper here (15 lines) rather than importing across files — keeps
the runtime import surface flat and matches the existing canonical pattern
in `skf-detect-scripts-assets.py:216`.

Hash-prefix normalization (writer-vs-reader compatibility): stored hashes
in `file_entries[].content_hash` carry a `sha256:` prefix by SKF convention
(see `skf-create-skill/references/extraction-patterns-tracing.md` §Provenance).
The reader-side normalization here is unconditionally safe — strip any
lowercase-alphanumeric prefix terminated by `:` before comparing, and
re-emit the stored value as-given in the diff record so reviewers can see
the original form. A bare-hex hash from a future writer would pass through
unchanged.

Subcommand:
  compare <provenance-map.json> <source-root>
      Emit JSON:
        {
          "added": ["<rel-path, forward-slash>", ...],
          "removed": ["<rel-path, forward-slash>", ...],
          "changed": [
            {"path": "<rel-path>", "stored_hash": "sha256:...",
             "current_hash": "sha256:..."}, ...
          ],
          "stats": {"added": N, "removed": N, "changed": N, "unchanged": N}
        }

      All paths are forward-slash relative to `<source-root>`. Stable sort
      on the lists for deterministic output (lexicographic on path).

CLI examples:
  uv run skf-compare-file-hashes.py compare prov-map.json /path/to/src

Exit codes:
  0  — comparison succeeded (including empty/well-formed input that yields
       all-empty drift lists)
  1  — user error (missing files, malformed JSON, unreadable paths)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable


# --------------------------------------------------------------------------
# Constants — mirror skf-detect-scripts-assets.py so the inverse walk
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


def load_file_entries(provenance_path: Path) -> list[dict]:
    """Extract `file_entries[]` from a provenance map. Accepts:
      - top-level object with a `file_entries` key (canonical)
      - top-level array (already extracted)
      - top-level object with NO `file_entries` field → empty list
        (a single-skill with no scripts/assets/docs may omit the field
        entirely per skill-sections.md §file_entries)

    Raises ValueError on read failure or structural defects.
    """
    try:
        text = provenance_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"failed to read provenance file {provenance_path}: {exc}"
        ) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"malformed JSON in provenance file {provenance_path}: {exc}"
        ) from exc

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


# --------------------------------------------------------------------------
# Walk — the inverse direction (source tree → candidate set)
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


def candidate_source_files(source_root: Path) -> Iterable[str]:
    """Yield POSIX relative paths under source_root that could be tracked
    as script / asset / doc file_entries.

    Selection rules:
      - File is under a SCRIPT_DIRS or ASSET_DIRS directory at any depth, OR
      - File path matches a DOC_DIR_PREFIXES synthetic namespace.
      - Binary extensions are excluded.
      - Generated/vendored directories are pruned from the walk.

    This is deliberately narrower than "every file" — audit-skill §4b only
    tracks files matching script/asset patterns. Treating every random
    source file as a candidate `added` row would drown real drift in noise.
    """
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
            if _segment_in_tracked_dir(rel_parts) or _matches_doc_prefix(rel_posix):
                yield rel_posix


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------


def compare(source_root: Path, provenance_path: Path) -> dict:
    """Compute added / removed / changed / unchanged for tracked file_entries.

    Stored hashes are normalized before comparison; the diff record carries
    the original stored value (writer-form) plus the freshly computed
    current value (always prefixed sha256:) so reviewers see both.
    """
    entries = load_file_entries(provenance_path)
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

    # Walk the source tree once; track which provenance entries are matched.
    candidates_on_disk = set(candidate_source_files(source_root))

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

    # Anything on disk but NOT in the provenance store is "added".
    added = sorted(candidates_on_disk - set(stored.keys()))

    return {
        "added": added,
        "removed": sorted(removed),
        "changed": sorted(changed, key=lambda r: r["path"]),
        "stats": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": unchanged_count,
        },
    }


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
    try:
        result = compare(source_root, provenance)
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
    p_cmp.set_defaults(func=_cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
