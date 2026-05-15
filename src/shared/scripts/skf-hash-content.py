# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Hash Content — SHA-256 hashing helpers for skill workflows.

Two patterns recur across the update-skill workflow's stage prose:

  1. **Single-file hash** — detect-changes.md §1b, when a candidate file is
     promoted into `brief.scope.include`, the LLM is asked to "compute SHA-256
     content hash of candidate.path" and emit a record
     `{path, heuristic, size_bytes, line_count, content_hash}` for
     `promoted_docs_new[]`. Deterministic file-read + hashlib.sha256.

  2. **Bulk-compare against provenance** — detect-changes.md §Category D,
     where the LLM is asked to "for each file_entry: compute current SHA-256
     content hash, compare against stored hash" and classify entries as
     MODIFIED_FILE / DELETED_FILE / (UNCHANGED). Same hashing primitive,
     iterated, plus a stat-and-compare. NEW_FILE detection is intentionally
     out of scope here — that lives in `skf-detect-scripts-assets.py`.

Subcommands:
  hash <path> [--include-path]
      Emit JSON {"content_hash": "sha256:...", "size_bytes": N, "line_count": L}
      for a single file. With --include-path, the record also includes
      "path": <as given>, so batch callers can collect records by streaming
      multiple invocations.

  compare <source-root> --provenance-map <path>
      Read `file_entries[]` from a provenance-map JSON and classify each row
      against the current source tree. Emits
        {
          "comparisons": [
            {"source_file": "...", "classification": "UNCHANGED|MODIFIED_FILE|DELETED_FILE",
             "stored_hash": "sha256:...", "current_hash": "sha256:..."|null,
             "current_size_bytes": N|null}, ...
          ],
          "stats": {"total": N, "unchanged": U, "modified": M, "deleted": D}
        }
      The provenance file must contain `file_entries` as a top-level array
      OR be the array itself (handles both schemas).

Hash format: `sha256:` prefix on a hex digest. Matches the convention used
by skf-detect-scripts-assets.py and the existing prose ("SHA-256 content
hash" — agnostic about prefix, but the prefix is the SKF convention to make
hashes self-describing for future algorithm migrations).

CLI examples:
  uv run skf-hash-content.py hash docs/AGENTS.md
  uv run skf-hash-content.py hash docs/AGENTS.md --include-path
  uv run skf-hash-content.py compare /path/to/source \\
      --provenance-map /path/to/provenance-map.json

Exit codes:
  0  — operation succeeded (including: file in compare missing on disk;
       its classification is DELETED_FILE, not an error)
  1  — user error (bad path, malformed JSON, missing required field)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# Hashing primitives
# --------------------------------------------------------------------------


def sha256_of_file(path: Path) -> str:
    """SHA-256 of file content, with sha256: prefix."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def count_lines(path: Path) -> int:
    """Count newlines in file content; 0 if unreadable."""
    n = 0
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                n += chunk.count(b"\n")
    except OSError:
        return 0
    return n


def hash_record(path: Path, *, include_path: bool = False) -> dict:
    """Build a single-file record: content_hash + size_bytes + line_count."""
    rec: dict = {
        "content_hash": sha256_of_file(path),
        "size_bytes": path.stat().st_size,
        "line_count": count_lines(path),
    }
    if include_path:
        rec = {"path": path.as_posix(), **rec}
    return rec


# --------------------------------------------------------------------------
# Provenance comparison
# --------------------------------------------------------------------------


UNCHANGED = "UNCHANGED"
MODIFIED_FILE = "MODIFIED_FILE"
DELETED_FILE = "DELETED_FILE"


def load_file_entries(provenance_path: Path) -> list[dict]:
    """Extract the file_entries list from a provenance file.

    Accepts two shapes:
      - top-level object with a `file_entries` key (canonical)
      - top-level array of entries (already-extracted)

    Returns a copy of the list. Raises ValueError on malformed JSON or
    missing key.
    """
    try:
        data = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"failed to read provenance file {provenance_path}: {exc}") from exc

    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict):
        entries = data.get("file_entries")
        if entries is None:
            raise ValueError(
                f"provenance file {provenance_path} has no `file_entries` field"
            )
        if not isinstance(entries, list):
            raise ValueError(
                f"`file_entries` in {provenance_path} is not an array"
            )
        return list(entries)
    raise ValueError(
        f"provenance file {provenance_path} must be an object or array; "
        f"got {type(data).__name__}"
    )


def classify_entry(source_root: Path, entry: dict) -> dict:
    """Classify a single file_entry against the current source tree."""
    source_file = entry.get("source_file")
    stored_hash = entry.get("content_hash")
    if not isinstance(source_file, str):
        raise ValueError(f"file_entry missing required `source_file`: {entry!r}")

    current = (source_root / source_file).resolve()
    # guard against ../.. escapes — resolved path must stay inside source_root
    try:
        current.relative_to(source_root.resolve())
    except ValueError:
        return {
            "source_file": source_file,
            "classification": DELETED_FILE,
            "stored_hash": stored_hash,
            "current_hash": None,
            "current_size_bytes": None,
        }

    if not current.is_file():
        return {
            "source_file": source_file,
            "classification": DELETED_FILE,
            "stored_hash": stored_hash,
            "current_hash": None,
            "current_size_bytes": None,
        }

    current_hash = sha256_of_file(current)
    if current_hash == stored_hash:
        classification = UNCHANGED
    else:
        classification = MODIFIED_FILE
    return {
        "source_file": source_file,
        "classification": classification,
        "stored_hash": stored_hash,
        "current_hash": current_hash,
        "current_size_bytes": current.stat().st_size,
    }


def compare(source_root: Path, provenance_path: Path) -> dict:
    entries = load_file_entries(provenance_path)
    comparisons = [classify_entry(source_root, entry) for entry in entries]
    counts = {UNCHANGED: 0, MODIFIED_FILE: 0, DELETED_FILE: 0}
    for c in comparisons:
        counts[c["classification"]] += 1
    return {
        "comparisons": comparisons,
        "stats": {
            "total": len(comparisons),
            "unchanged": counts[UNCHANGED],
            "modified": counts[MODIFIED_FILE],
            "deleted": counts[DELETED_FILE],
        },
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_hash(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    rec = hash_record(path, include_path=args.include_path)
    json.dump(rec, sys.stdout)
    sys.stdout.write("\n")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    source_root = Path(args.source_root)
    provenance = Path(args.provenance_map)
    if not source_root.is_dir():
        print(f"error: source root not a directory: {source_root}", file=sys.stderr)
        return 1
    if not provenance.is_file():
        print(f"error: provenance map not found: {provenance}", file=sys.stderr)
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
        prog="skf-hash-content",
        description="SHA-256 hashing helpers: single-file record or bulk-compare against provenance.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_hash = sub.add_parser("hash", help="emit hash record for a single file")
    p_hash.add_argument("path", help="path to the file")
    p_hash.add_argument(
        "--include-path",
        action="store_true",
        help="include the path string in the emitted record",
    )
    p_hash.set_defaults(func=_cmd_hash)

    p_cmp = sub.add_parser(
        "compare",
        help="classify provenance file_entries[] against current source tree",
    )
    p_cmp.add_argument("source_root", help="path to the source tree root")
    p_cmp.add_argument(
        "--provenance-map",
        required=True,
        help="path to provenance-map.json (object with file_entries[] or bare array)",
    )
    p_cmp.set_defaults(func=_cmd_compare)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
