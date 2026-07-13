#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Deterministic NEW_FILE detection for skf-update-skill (detect-changes Category D).

`skf-hash-content compare` classifies files already tracked in the provenance
map (UNCHANGED / MODIFIED_FILE / DELETED_FILE) but by design cannot report a
file that is present in source yet absent from the provenance map — a NEW_FILE.
Deriving that set is a set-difference plus a filter with exactly one correct
answer per input: take every `source_file` in the scripts/assets inventory
(emitted by `skf-detect-scripts-assets detect`), subtract the paths already in
`file_entries[].source_file`, and set aside any user-authored `[MANUAL]` path.
Doing that subtraction in the prompt drifts across runs; doing it here is
byte-stable.

Usage:
  skf-detect-scripts-assets.py detect <source-root> \
    | skf-new-file-diff.py <provenance-map-path>

Reads the detect JSON on stdin (needs `scripts_inventory[]` and
`assets_inventory[]`, each row carrying `source_file`). Reads the provenance
map at the path argument (canonical `{file_entries: [...]}` object, or a bare
array of entries).

Output JSON (stdout):
  {
    "new_files":       [ {"source_file": "...", "kind": "script|asset"}, ... ],
    "skipped_manual":  [ "...", ... ],   # under scripts/[MANUAL]/ or assets/[MANUAL]/
    "already_tracked": [ "...", ... ],   # present in file_entries
    "stats": {"inventory_total": N, "new": N,
              "skipped_manual": N, "already_tracked": N}
  }

All three arrays are sorted by source_file; new_files carries the kind of the
inventory it came from (scripts -> "script", assets -> "asset"). A path found
in both inventories is counted once, resolved as "script".

Exit codes:
  0  success
  2  bad input (unreadable/invalid stdin JSON, missing/invalid provenance map)
"""

import json
import re
import sys
from pathlib import Path

# scripts/[MANUAL]/... or assets/[MANUAL]/... anywhere in the (posix) path
_MANUAL_RE = re.compile(r"(?:^|/)(?:scripts|assets)/\[MANUAL\]/")


def _fail(msg: str) -> "NoReturn":  # type: ignore[valid-type]
    print(json.dumps({"error": msg}), file=sys.stderr)
    sys.exit(2)


def _posix(p: str) -> str:
    return p.replace("\\", "/")


def load_tracked_source_files(provenance_path: Path) -> set[str]:
    """Return the set of file_entries[].source_file already in the provenance map."""
    try:
        data = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _fail(f"failed to read provenance map {provenance_path}: {exc}")

    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        entries = data.get("file_entries")
        if entries is None:
            _fail(f"provenance map {provenance_path} has no `file_entries` field")
        if not isinstance(entries, list):
            _fail(f"`file_entries` in {provenance_path} is not an array")
    else:
        _fail(
            f"provenance map {provenance_path} must be an object or array; "
            f"got {type(data).__name__}"
        )

    tracked: set[str] = set()
    for entry in entries:
        if isinstance(entry, dict):
            sf = entry.get("source_file")
            if isinstance(sf, str) and sf:
                tracked.add(_posix(sf))
    return tracked


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


def diff(detect: dict, tracked: set[str]) -> dict:
    new_files: list[dict] = []
    skipped_manual: list[str] = []
    already_tracked: list[str] = []

    inventory = collect_inventory(detect)
    for sf, kind in inventory:
        if sf in tracked:
            already_tracked.append(sf)
        elif _MANUAL_RE.search(sf):
            skipped_manual.append(sf)
        else:
            new_files.append({"source_file": sf, "kind": kind})

    return {
        "new_files": new_files,
        "skipped_manual": sorted(skipped_manual),
        "already_tracked": sorted(already_tracked),
        "stats": {
            "inventory_total": len(inventory),
            "new": len(new_files),
            "skipped_manual": len(skipped_manual),
            "already_tracked": len(already_tracked),
        },
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        _fail("usage: skf-new-file-diff.py <provenance-map-path>  (detect JSON on stdin)")

    provenance_path = Path(argv[1])
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

    tracked = load_tracked_source_files(provenance_path)
    result = diff(detect, tracked)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
